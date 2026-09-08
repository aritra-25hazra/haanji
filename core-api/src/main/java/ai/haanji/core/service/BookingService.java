package ai.haanji.core.service;

import ai.haanji.core.domain.*;
import ai.haanji.core.pramaan.ConfirmationProof;
import ai.haanji.core.pramaan.LedgerService;
import ai.haanji.core.repo.Repositories.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.*;
import java.util.*;

/**
 * Booking, cancelling and offering slots.
 *
 * <p>Two rules are load bearing here. First, a slot is never handed out on the
 * strength of an in-memory check: the exclusion constraint in PostgreSQL is
 * what actually prevents a double booking, and this class treats its violation
 * as an expected outcome rather than an error. Second, a booking and its
 * receipt are written in one transaction, so the ledger cannot disagree with
 * the calendar.
 */
@Service
public class BookingService {

    private static final Logger log = LoggerFactory.getLogger(BookingService.class);

    private final AppointmentRepository appointments;
    private final ServiceRepository services;
    private final StaffRepository staff;
    private final CustomerRepository customers;
    private final AvailabilityService availability;
    private final LedgerService ledger;

    public BookingService(AppointmentRepository appointments, ServiceRepository services,
                          StaffRepository staff, CustomerRepository customers,
                          AvailabilityService availability, LedgerService ledger) {
        this.appointments = appointments;
        this.services = services;
        this.staff = staff;
        this.customers = customers;
        this.availability = availability;
        this.ledger = ledger;
    }

    public record BookingRequest(String serviceName, LocalDate date, LocalTime time,
                                 String staffName, String customerName, String phone,
                                 UUID conversationId, Appointment.Source source,
                                 ConfirmationProof proof, String transcriptExcerpt,
                                 int agentConfigVersion) { }

    public record BookingResult(Appointment appointment, String receiptCode,
                                String serviceName, String staffName) { }

    @Transactional
    public BookingResult book(UUID tenantId, BookingRequest request, ZoneId zone) {
        ServiceOffering offering = services.findByTenantIdAndName(tenantId, request.serviceName())
                .orElseThrow(() -> new UnknownServiceException(request.serviceName()));

        StaffMember member = request.staffName() != null
                ? staff.findByTenantIdAndName(tenantId, request.staffName())
                       .orElseThrow(() -> new UnknownStaffException(request.staffName()))
                : pickStaff(offering);

        Instant startsAt = ZonedDateTime.of(request.date(), request.time(), zone).toInstant();
        Instant endsAt = startsAt.plus(Duration.ofMinutes(offering.getDurationMin()));

        if (startsAt.isBefore(Instant.now())) {
            throw new SlotUnavailableException("that time has already passed");
        }
        if (!availability.isWithinWorkingHours(tenantId, member.getId(), request.date(),
                request.time(), offering.getDurationMin())) {
            throw new SlotUnavailableException("that time is outside working hours");
        }

        Customer customer = upsertCustomer(tenantId, request.phone(), request.customerName());
        Appointment appointment = new Appointment(tenantId, offering.getId(), member.getId(),
                customer == null ? null : customer.getId(), startsAt, endsAt, request.source());

        try {
            appointments.saveAndFlush(appointment);
        } catch (DataIntegrityViolationException exclusion) {
            // The exclusion constraint fired: somebody else took the slot between
            // the availability read and this write. This is normal under load.
            log.info("slot collision tenant={} staff={} at={}", tenantId, member.getId(), startsAt);
            throw new SlotUnavailableException("that slot was taken a moment ago");
        }

        Map<String, Object> args = new LinkedHashMap<>();
        args.put("appointment_id", appointment.getId().toString());
        args.put("service", offering.getName());
        args.put("staff", member.getName());
        args.put("starts_at", startsAt.toString());
        args.put("customer_name", request.customerName());
        args.put("phone", request.phone());

        Receipt receipt = ledger.append(tenantId, request.conversationId(), "book_appointment",
                args, request.proof(), request.transcriptExcerpt(),
                request.agentConfigVersion(), true);
        appointment.attachReceipt(receipt.getShortCode());

        if (customer != null) {
            customer.recordVisit(offering.getName(), request.date());
        }
        return new BookingResult(appointment, receipt.getShortCode(),
                offering.getName(), member.getName());
    }

    @Transactional
    public String cancel(UUID tenantId, UUID appointmentId, ConfirmationProof proof,
                         UUID conversationId, String excerpt, int agentConfigVersion) {
        Appointment appointment = appointments.findById(appointmentId)
                .filter(a -> a.getTenantId().equals(tenantId))
                .orElseThrow(() -> new UnknownAppointmentException(appointmentId));
        if (!appointment.isConfirmed()) {
            throw new IllegalStateException("that appointment is not confirmed");
        }
        Receipt receipt = ledger.append(tenantId, conversationId, "cancel_appointment",
                Map.of("appointment_id", appointmentId.toString()), proof, excerpt,
                agentConfigVersion, true);
        appointment.cancel();
        return receipt.getShortCode();
    }

    private StaffMember pickStaff(ServiceOffering offering) {
        return offering.getStaff().stream().filter(StaffMember::isActive).findFirst()
                .orElseThrow(() -> new UnknownStaffException(
                        "no active staff can perform " + offering.getName()));
    }

    private Customer upsertCustomer(UUID tenantId, String phone, String name) {
        if (phone == null || phone.isBlank()) {
            return null;
        }
        return customers.findByTenantIdAndPhone(tenantId, phone)
                .map(existing -> { existing.rename(name); return existing; })
                .orElseGet(() -> customers.save(new Customer(tenantId, phone, name)));
    }

    public static class SlotUnavailableException extends RuntimeException {
        public SlotUnavailableException(String message) { super(message); }
    }
    public static class UnknownServiceException extends RuntimeException {
        public UnknownServiceException(String name) { super("unknown service: " + name); }
    }
    public static class UnknownStaffException extends RuntimeException {
        public UnknownStaffException(String name) { super("unknown staff: " + name); }
    }
    public static class UnknownAppointmentException extends RuntimeException {
        public UnknownAppointmentException(UUID id) { super("unknown appointment: " + id); }
    }
}
