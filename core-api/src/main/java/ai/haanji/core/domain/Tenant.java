package ai.haanji.core.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "tenants")
public class Tenant {

    public enum Status { ACTIVE, SUSPENDED, CLOSED }

    @Id @GeneratedValue
    @Column(name = "tenant_id")
    private UUID id;

    @Column(nullable = false, unique = true)
    private String slug;

    @Column(name = "business_name", nullable = false)
    private String businessName;

    @Column(name = "pack_id", nullable = false)
    private String packId;

    @Column(name = "pack_version", nullable = false)
    private int packVersion = 1;

    @Column(nullable = false)
    private String timezone = "Asia/Kolkata";

    @Column(nullable = false)
    private String locale = "hi-IN";

    @Column(name = "phone_number")
    private String phoneNumber;

    @Column(name = "whatsapp_number")
    private String whatsappNumber;

    @Column(nullable = false)
    private String plan = "TRIAL";

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Status status = Status.ACTIVE;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    protected Tenant() { }

    public Tenant(String slug, String businessName, String packId) {
        this.slug = slug;
        this.businessName = businessName;
        this.packId = packId;
    }

    public UUID getId() { return id; }
    public String getSlug() { return slug; }
    public String getBusinessName() { return businessName; }
    public String getPackId() { return packId; }
    public int getPackVersion() { return packVersion; }
    public String getTimezone() { return timezone; }
    public String getPhoneNumber() { return phoneNumber; }
    public String getWhatsappNumber() { return whatsappNumber; }
    public String getPlan() { return plan; }
    public Status getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }

    public void setPack(String packId, int version) {
        this.packId = packId;
        this.packVersion = version;
    }
    public void setPhoneNumber(String v) { this.phoneNumber = v; }
    public void setWhatsappNumber(String v) { this.whatsappNumber = v; }
    public void suspend() { this.status = Status.SUSPENDED; }
    public boolean isActive() { return status == Status.ACTIVE; }
}
