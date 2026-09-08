package ai.haanji.core.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "leads")
public class Lead {

    public enum Status { NEW, CALLED, CONVERTED, CLOSED }

    @Id @GeneratedValue
    @Column(name = "lead_id")
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private UUID tenantId;

    private String name;
    private String phone;

    @Column(nullable = false)
    private String intent;

    private String note;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Status status = Status.NEW;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    protected Lead() { }

    public Lead(UUID tenantId, String name, String phone, String intent, String note) {
        this.tenantId = tenantId;
        this.name = name;
        this.phone = phone;
        this.intent = intent;
        this.note = note;
    }

    public UUID getId() { return id; }
    public UUID getTenantId() { return tenantId; }
    public String getName() { return name; }
    public String getPhone() { return phone; }
    public String getIntent() { return intent; }
    public String getNote() { return note; }
    public Status getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }

    public void markCalled() { this.status = Status.CALLED; }
    public void markConverted() { this.status = Status.CONVERTED; }
}
