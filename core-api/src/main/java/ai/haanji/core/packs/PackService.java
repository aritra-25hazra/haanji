package ai.haanji.core.packs;

import ai.haanji.core.domain.*;
import ai.haanji.core.repo.Repositories.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import jakarta.persistence.EntityManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.IOException;
import java.nio.file.*;
import java.util.*;

/**
 * Loads a vertical pack and materialises it as a tenant.
 *
 * <p>Onboarding a business is running this once. That is the commercial point
 * of the pack format: the work of supporting a new industry is done by whoever
 * writes the YAML, not by an engineer, and the same file drives the engine's
 * persona, its refusals, its vocabulary and its acceptance tests.
 */
@Service
public class PackService {

    private static final Logger log = LoggerFactory.getLogger(PackService.class);
    private static final ObjectMapper YAML = new ObjectMapper(new YAMLFactory());
    private static final List<String> DAYS =
            List.of("mon", "tue", "wed", "thu", "fri", "sat", "sun");

    private final Path directory;
    private final TenantRepository tenants;
    private final ServiceRepository services;
    private final StaffRepository staff;
    private final EntityManager em;

    public PackService(@Value("${haanji.packs.directory}") String directory,
                       TenantRepository tenants, ServiceRepository services,
                       StaffRepository staff, EntityManager em) {
        this.directory = Path.of(directory);
        this.tenants = tenants;
        this.services = services;
        this.staff = staff;
        this.em = em;
    }

    public List<String> available() {
        try (var stream = Files.list(directory)) {
            return stream.map(p -> p.getFileName().toString())
                    .filter(n -> n.endsWith(".yaml"))
                    .map(n -> n.substring(0, n.length() - 5))
                    .sorted().toList();
        } catch (IOException e) {
            log.warn("no pack directory at {}", directory);
            return List.of();
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> read(String packId) {
        try {
            return YAML.readValue(directory.resolve(packId + ".yaml").toFile(), Map.class);
        } catch (IOException e) {
            throw new IllegalArgumentException("no pack " + packId, e);
        }
    }

    @Transactional
    @SuppressWarnings("unchecked")
    public Tenant onboard(String slug, String packId) {
        Map<String, Object> pack = read(packId);
        Map<String, Object> persona = (Map<String, Object>) pack.getOrDefault("persona", Map.of());
        String businessName = String.valueOf(
                persona.getOrDefault("business_name", pack.getOrDefault("display_name", slug)));

        Tenant tenant = tenants.save(new Tenant(slug, businessName, packId));

        Map<String, StaffMember> byName = new LinkedHashMap<>();
        for (Object person : (List<Object>) pack.getOrDefault("staff", List.of())) {
            StaffMember member = staff.save(new StaffMember(tenant.getId(), String.valueOf(person),
                    String.valueOf(pack.getOrDefault("staff_role", "staff"))));
            byName.put(member.getName(), member);
        }

        for (Object raw : (List<Object>) pack.getOrDefault("services", List.of())) {
            Map<String, Object> s = (Map<String, Object>) raw;
            ServiceOffering offering = new ServiceOffering(tenant.getId(),
                    String.valueOf(s.get("name")),
                    ((Number) s.getOrDefault("duration_min", 30)).intValue(),
                    s.get("price_inr") == null ? null : ((Number) s.get("price_inr")).intValue());
            offering.setPrepNote((String) s.get("prep_note"));
            List<Object> people = (List<Object>) s.getOrDefault("staff", List.of());
            (people.isEmpty() ? byName.keySet() : people.stream().map(String::valueOf).toList())
                    .forEach(name -> Optional.ofNullable(byName.get(name))
                            .ifPresent(offering::addStaff));
            services.save(offering);
        }

        ((Map<String, Object>) pack.getOrDefault("hours", Map.of()))
                .forEach((spec, value) -> {
                    if (value == null) {
                        return;                       // a closed day has no row at all
                    }
                    List<String> window = (List<String>) value;
                    for (int weekday : expandDays(spec)) {
                        em.createNativeQuery("""
                                INSERT INTO working_hours
                                    (tenant_id, staff_id, weekday, open_min, close_min,
                                     break_start, break_end)
                                VALUES (:tenant, NULL, :weekday, :open, :close, :bs, :be)
                                ON CONFLICT DO NOTHING
                                """)
                                .setParameter("tenant", tenant.getId())
                                .setParameter("weekday", weekday)
                                .setParameter("open", minutes(window.get(0)))
                                .setParameter("close", minutes(window.get(1)))
                                .setParameter("bs", window.size() > 2 ? minutes(window.get(2)) : null)
                                .setParameter("be", window.size() > 3 ? minutes(window.get(3)) : null)
                                .executeUpdate();
                    }
                });

        for (Object raw : (List<Object>) pack.getOrDefault("knowledge", List.of())) {
            Map<String, Object> k = (Map<String, Object>) raw;
            em.createNativeQuery("""
                    INSERT INTO knowledge_entries (tenant_id, question, answer, tags)
                    VALUES (:tenant, :q, :a, :tags)
                    """)
                    .setParameter("tenant", tenant.getId())
                    .setParameter("q", String.valueOf(k.get("q")))
                    .setParameter("a", String.valueOf(k.get("a")))
                    .setParameter("tags", ((List<Object>) k.getOrDefault("tags", List.of()))
                            .stream().map(String::valueOf).toArray(String[]::new))
                    .executeUpdate();
        }

        log.info("onboarded tenant={} from pack={} with {} services",
                tenant.getSlug(), packId, services.findByTenantIdAndActiveTrue(tenant.getId()).size());
        return tenant;
    }

    static List<Integer> expandDays(String spec) {
        List<Integer> out = new ArrayList<>();
        for (String part : spec.replace(" ", "").split(",")) {
            if (part.contains("-")) {
                String[] ends = part.split("-");
                int from = DAYS.indexOf(ends[0].substring(0, 3).toLowerCase());
                int to = DAYS.indexOf(ends[1].substring(0, 3).toLowerCase());
                for (int d = from; ; d = (d + 1) % 7) {
                    out.add(d);
                    if (d == to) {
                        break;
                    }
                }
            } else if (!part.isBlank()) {
                out.add(DAYS.indexOf(part.substring(0, 3).toLowerCase()));
            }
        }
        return out;
    }

    static int minutes(String hhmm) {
        String[] parts = hhmm.split(":");
        return Integer.parseInt(parts[0]) * 60 + Integer.parseInt(parts[1]);
    }
}
