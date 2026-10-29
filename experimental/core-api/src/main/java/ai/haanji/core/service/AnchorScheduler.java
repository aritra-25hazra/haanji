package ai.haanji.core.service;

import ai.haanji.core.domain.Receipt;
import ai.haanji.core.pramaan.ChainVerifier;
import ai.haanji.core.pramaan.SigningKeyStore;
import ai.haanji.core.repo.Repositories.ReceiptRepository;
import ai.haanji.core.repo.Repositories.TenantRepository;
import jakarta.persistence.EntityManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.*;
import java.util.List;

/**
 * Publishes one signed Merkle root per tenant per day.
 *
 * <p>Hash chaining alone proves that history has not been edited, but not that
 * it has not been rewritten wholesale by someone who controls the database and
 * the signing key. A daily root, published where the operator cannot quietly
 * replace it, closes that gap: a rewritten history would have to reproduce
 * every anchor ever published.
 */
@Service
public class AnchorScheduler {

    private static final Logger log = LoggerFactory.getLogger(AnchorScheduler.class);

    private final TenantRepository tenants;
    private final ReceiptRepository receipts;
    private final ChainVerifier verifier;
    private final SigningKeyStore keys;
    private final EntityManager em;

    public AnchorScheduler(TenantRepository tenants, ReceiptRepository receipts,
                           ChainVerifier verifier, SigningKeyStore keys, EntityManager em) {
        this.tenants = tenants;
        this.receipts = receipts;
        this.verifier = verifier;
        this.keys = keys;
        this.em = em;
    }

    @Scheduled(cron = "${haanji.ledger.anchor-cron:0 15 0 * * *}", zone = "Asia/Kolkata")
    public void anchorYesterday() {
        LocalDate day = LocalDate.now(ZoneId.of("Asia/Kolkata")).minusDays(1);
        tenants.findAll().forEach(tenant -> {
            try {
                anchor(tenant.getId(), day, ZoneId.of(tenant.getTimezone()));
            } catch (RuntimeException e) {
                log.error("could not anchor tenant={} day={}", tenant.getId(), day, e);
            }
        });
    }

    @Transactional
    public void anchor(java.util.UUID tenantId, LocalDate day, ZoneId zone) {
        Instant from = day.atStartOfDay(zone).toInstant();
        Instant until = day.plusDays(1).atStartOfDay(zone).toInstant();
        List<Receipt> ofDay = receipts.findByTenantIdOrderBySeqAsc(tenantId).stream()
                .filter(r -> !r.getOccurredAt().isBefore(from) && r.getOccurredAt().isBefore(until))
                .toList();
        if (ofDay.isEmpty()) {
            return;
        }
        byte[] root = verifier.merkleRoot(ofDay);
        SigningKeyStore.Key key = keys.activeKeyFor(tenantId);
        byte[] signature = keys.sign(key, root);

        em.createNativeQuery("""
                INSERT INTO daily_anchors
                    (tenant_id, day, first_seq, last_seq, merkle_root, signature, key_id)
                VALUES (:tenant, :day, :first, :last, :root, :sig, :key)
                ON CONFLICT (tenant_id, day) DO NOTHING
                """)
                .setParameter("tenant", tenantId)
                .setParameter("day", day)
                .setParameter("first", ofDay.getFirst().getSeq())
                .setParameter("last", ofDay.getLast().getSeq())
                .setParameter("root", root)
                .setParameter("sig", signature)
                .setParameter("key", key.keyId())
                .executeUpdate();
        log.info("anchored tenant={} day={} receipts={}", tenantId, day, ofDay.size());
    }
}
