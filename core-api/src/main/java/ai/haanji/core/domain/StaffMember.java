package ai.haanji.core.domain;

import jakarta.persistence.*;
import java.util.UUID;

@Entity
@Table(name = "staff_members")
public class StaffMember {

    @Id @GeneratedValue
    @Column(name = "staff_id")
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private UUID tenantId;

    @Column(nullable = false)
    private String name;

    private String role;

    @Column(nullable = false)
    private boolean active = true;

    protected StaffMember() { }

    public StaffMember(UUID tenantId, String name, String role) {
        this.tenantId = tenantId;
        this.name = name;
        this.role = role;
    }

    public UUID getId() { return id; }
    public UUID getTenantId() { return tenantId; }
    public String getName() { return name; }
    public String getRole() { return role; }
    public boolean isActive() { return active; }
}
