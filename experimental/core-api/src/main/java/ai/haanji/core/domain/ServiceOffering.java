package ai.haanji.core.domain;

import jakarta.persistence.*;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;

/** One bookable thing the business sells. Named ServiceOffering rather than
 *  Service so it never reads as a Spring bean. */
@Entity
@Table(name = "services")
public class ServiceOffering {

    @Id @GeneratedValue
    @Column(name = "service_id")
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private UUID tenantId;

    @Column(nullable = false)
    private String name;

    @Column(name = "duration_min", nullable = false)
    private int durationMin;

    @Column(name = "price_inr")
    private Integer priceInr;

    @Column(name = "prep_note")
    private String prepNote;

    @Column(nullable = false)
    private boolean active = true;

    @ManyToMany
    @JoinTable(name = "service_staff",
            joinColumns = @JoinColumn(name = "service_id"),
            inverseJoinColumns = @JoinColumn(name = "staff_id"))
    private Set<StaffMember> staff = new LinkedHashSet<>();

    protected ServiceOffering() { }

    public ServiceOffering(UUID tenantId, String name, int durationMin, Integer priceInr) {
        this.tenantId = tenantId;
        this.name = name;
        this.durationMin = durationMin;
        this.priceInr = priceInr;
    }

    public UUID getId() { return id; }
    public UUID getTenantId() { return tenantId; }
    public String getName() { return name; }
    public int getDurationMin() { return durationMin; }
    public Integer getPriceInr() { return priceInr; }
    public String getPrepNote() { return prepNote; }
    public boolean isActive() { return active; }
    public Set<StaffMember> getStaff() { return staff; }

    public void setPrepNote(String v) { this.prepNote = v; }
    public void addStaff(StaffMember member) { staff.add(member); }
    public void deactivate() { this.active = false; }
}
