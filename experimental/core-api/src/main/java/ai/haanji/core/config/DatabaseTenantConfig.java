package ai.haanji.core.config;

import ai.haanji.core.service.TenantContext;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

import java.util.UUID;

/**
 * Pushes the request's tenant into the database session.
 *
 * <p>PostgreSQL row level security reads {@code haanji.tenant_id}, so this is
 * what turns the application-level binding into an enforced one. Without it a
 * repository method that forgets its {@code tenantId} argument would happily
 * return every tenant's rows; with it, the query returns nothing instead. The
 * setting is scoped to the transaction, so a pooled connection cannot carry it
 * into the next request.
 */
@Aspect
@Component
public class DatabaseTenantConfig {

    @PersistenceContext
    private EntityManager em;

    @Around("@annotation(org.springframework.transaction.annotation.Transactional)")
    public Object bindTenant(ProceedingJoinPoint joinPoint) throws Throwable {
        UUID tenantId = TenantContext.currentOrNull();
        if (tenantId != null) {
            em.createNativeQuery("SELECT set_config('haanji.tenant_id', :tenant, true)")
                    .setParameter("tenant", tenantId.toString())
                    .getSingleResult();
        }
        return joinPoint.proceed();
    }
}
