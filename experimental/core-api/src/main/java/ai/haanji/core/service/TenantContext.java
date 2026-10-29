package ai.haanji.core.service;

import java.util.UUID;

/**
 * The tenant the current request belongs to.
 *
 * <p>Held in a thread local and set by a servlet filter, then pushed down to
 * the database session so PostgreSQL row level security can enforce isolation
 * as well. Two independent mechanisms guard the same boundary, because
 * multi-tenant leakage is the one bug that ends a business like this.
 */
public final class TenantContext {

    private static final ThreadLocal<UUID> CURRENT = new ThreadLocal<>();

    private TenantContext() { }

    public static void set(UUID tenantId) {
        CURRENT.set(tenantId);
    }

    public static UUID require() {
        UUID id = CURRENT.get();
        if (id == null) {
            throw new IllegalStateException("no tenant bound to this request");
        }
        return id;
    }

    public static UUID currentOrNull() {
        return CURRENT.get();
    }

    public static void clear() {
        CURRENT.remove();
    }
}
