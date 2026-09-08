package ai.haanji.core.repo;

import ai.haanji.core.domain.*;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * All repositories in one file on purpose: they are declarations, not logic,
 * and keeping them together makes the data access surface of the whole service
 * readable in one screen. Anything with behaviour belongs in a service class.
 */
public final class Repositories {
    private Repositories() { }

    public interface TenantRepository extends JpaRepository<Tenant, UUID> {
        Optional<Tenant> findBySlug(String slug);
        Optional<Tenant> findByPhoneNumber(String phoneNumber);
        Optional<Tenant> findByWhatsappNumber(String whatsappNumber);
    }

    public interface ServiceRepository extends JpaRepository<ServiceOffering, UUID> {
        List<ServiceOffering> findByTenantIdAndActiveTrue(UUID tenantId);
        Optional<ServiceOffering> findByTenantIdAndName(UUID tenantId, String name);
    }

    public interface StaffRepository extends JpaRepository<StaffMember, UUID> {
        List<StaffMember> findByTenantIdAndActiveTrue(UUID tenantId);
        Optional<StaffMember> findByTenantIdAndName(UUID tenantId, String name);
    }

    public interface CustomerRepository extends JpaRepository<Customer, UUID> {
        Optional<Customer> findByTenantIdAndPhone(UUID tenantId, String phone);
    }

    public interface AppointmentRepository extends JpaRepository<Appointment, UUID> {

        /** Overlap, not containment: an appointment that starts before the
         *  window and runs into it still occupies the staff member. */
        @Query("""
               select a from Appointment a
               where a.tenantId = :tenantId and a.status = :status
                 and a.startsAt < :until and a.endsAt > :from
               order by a.startsAt
               """)
        List<Appointment> findBetween(@Param("tenantId") UUID tenantId,
                                      @Param("from") Instant from,
                                      @Param("until") Instant until,
                                      @Param("status") Appointment.Status status);

        default List<Appointment> findConfirmedBetween(UUID tenantId, Instant from,
                                                       Instant until) {
            return findBetween(tenantId, from, until, Appointment.Status.CONFIRMED);
        }

        @Query("""
               select a from Appointment a
               where a.tenantId = :tenantId and a.customerId = :customerId
                 and a.status = :status and a.startsAt > :after
               order by a.startsAt
               """)
        List<Appointment> findForCustomer(@Param("tenantId") UUID tenantId,
                                          @Param("customerId") UUID customerId,
                                          @Param("after") Instant after,
                                          @Param("status") Appointment.Status status);

        default List<Appointment> findUpcomingForCustomer(UUID tenantId, UUID customerId,
                                                          Instant after) {
            return findForCustomer(tenantId, customerId, after, Appointment.Status.CONFIRMED);
        }

        long countByTenantIdAndStatus(UUID tenantId, Appointment.Status status);
    }

    public interface LeadRepository extends JpaRepository<Lead, UUID> {
        List<Lead> findByTenantIdAndStatusOrderByCreatedAtDesc(UUID tenantId, Lead.Status status);
        long countByTenantIdAndStatus(UUID tenantId, Lead.Status status);
    }

    public interface ConversationRepository extends JpaRepository<Conversation, UUID> {
        List<Conversation> findTop50ByTenantIdOrderByStartedAtDesc(UUID tenantId);

        @Query("""
               select c.outcome, count(c) from Conversation c
               where c.tenantId = :tenantId and c.startedAt >= :since
               group by c.outcome
               """)
        List<Object[]> countByOutcomeSince(@Param("tenantId") UUID tenantId,
                                           @Param("since") Instant since);
    }

    public interface ReceiptRepository extends JpaRepository<Receipt, UUID> {

        List<Receipt> findByTenantIdOrderBySeqAsc(UUID tenantId);
        Optional<Receipt> findByTenantIdAndShortCode(UUID tenantId, String shortCode);
        List<Receipt> findByConversationIdOrderBySeqAsc(UUID conversationId);

        @Query("select max(r.seq) from Receipt r where r.tenantId = :tenantId")
        Optional<Long> findMaxSeq(@Param("tenantId") UUID tenantId);

        @Query("""
               select r from Receipt r
               where r.tenantId = :tenantId and r.seq between :first and :last
               order by r.seq
               """)
        List<Receipt> findRange(@Param("tenantId") UUID tenantId,
                                @Param("first") long first, @Param("last") long last);
    }
}
