package ai.haanji.core.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "appointments")
public class Appointment {

    public enum Status { CONFIRMED, CANCELLED, NO_SHOW, DONE }
    public enum Source { VOICE, WHATSAPP, WEB, MANUAL }

    @Id @GeneratedValue
    @Column(name = "appointment_id")
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private UUID tenantId;

    @Column(name = "service_id", nullable = false)
    private UUID serviceId;

    @Column(name = "staff_id", nullable = false)
    private UUID staffId;

    @Column(name = "customer_id")
    private UUID customerId;

    @Column(name = "starts_at", nullable = false)
    private Instant startsAt;

    @Column(name = "ends_at", nullable = false)
    private Instant endsAt;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Status status = Status.CONFIRMED;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Source source = Source.VOICE;

    /** The Pramaan receipt that authorised this row. Null only for rows a human
     *  created directly in the console, which carry their own audit trail. */
    @Column(name = "receipt_code")
    private String receiptCode;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    protected Appointment() { }

    public Appointment(UUID tenantId, UUID serviceId, UUID staffId, UUID customerId,
                       Instant startsAt, Instant endsAt, Source source) {
        this.tenantId = tenantId;
        this.serviceId = serviceId;
        this.staffId = staffId;
        this.customerId = customerId;
        this.startsAt = startsAt;
        this.endsAt = endsAt;
        this.source = source;
    }

    public UUID getId() { return id; }
    public UUID getTenantId() { return tenantId; }
    public UUID getServiceId() { return serviceId; }
    public UUID getStaffId() { return staffId; }
    public UUID getCustomerId() { return customerId; }
    public Instant getStartsAt() { return startsAt; }
    public Instant getEndsAt() { return endsAt; }
    public Status getStatus() { return status; }
    public Source getSource() { return source; }
    public String getReceiptCode() { return receiptCode; }

    public void attachReceipt(String code) { this.receiptCode = code; }
    public void cancel() { this.status = Status.CANCELLED; }
    public boolean isConfirmed() { return status == Status.CONFIRMED; }
}
