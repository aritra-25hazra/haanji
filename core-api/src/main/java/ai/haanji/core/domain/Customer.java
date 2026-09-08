package ai.haanji.core.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

@Entity
@Table(name = "customers")
public class Customer {

    @Id @GeneratedValue
    @Column(name = "customer_id")
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private UUID tenantId;

    @Column(nullable = false)
    private String phone;

    private String name;

    @Column(name = "last_service")
    private String lastService;

    @Column(name = "last_visit")
    private LocalDate lastVisit;

    @Column(nullable = false)
    private int visits = 0;

    @Column(name = "consent_sms", nullable = false)
    private boolean consentSms = true;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    protected Customer() { }

    public Customer(UUID tenantId, String phone, String name) {
        this.tenantId = tenantId;
        this.phone = phone;
        this.name = name;
    }

    public UUID getId() { return id; }
    public UUID getTenantId() { return tenantId; }
    public String getPhone() { return phone; }
    public String getName() { return name; }
    public String getLastService() { return lastService; }
    public LocalDate getLastVisit() { return lastVisit; }
    public int getVisits() { return visits; }
    public boolean hasSmsConsent() { return consentSms; }

    public void recordVisit(String service, LocalDate on) {
        this.lastService = service;
        this.lastVisit = on;
        this.visits++;
    }
    public void rename(String name) { if (name != null && !name.isBlank()) this.name = name; }
    public void withdrawSmsConsent() { this.consentSms = false; }
}
