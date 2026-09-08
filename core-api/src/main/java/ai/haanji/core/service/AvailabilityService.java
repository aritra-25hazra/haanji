package ai.haanji.core.service;

import ai.haanji.core.domain.Appointment;
import ai.haanji.core.domain.ServiceOffering;
import ai.haanji.core.domain.StaffMember;
import ai.haanji.core.repo.Repositories.*;
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.*;
import java.util.*;

/**
 * Free slots.
 *
 * <p>This is the read the voice engine speculates on, so it is written to be
 * cheap and side-effect free: one indexed range query per request, no writes,
 * no caches that could go stale between the speculation and the real call.
 */
@Service
public class AvailabilityService {

    public record Slot(LocalDate date, LocalTime time, UUID staffId, String staffName) { }

    private record Hours(int openMin, int closeMin, Integer breakStart, Integer breakEnd) { }

    private final AppointmentRepository appointments;
    private final ServiceRepository services;
    private final StaffRepository staff;
    private final EntityManager em;

    public AvailabilityService(AppointmentRepository appointments, ServiceRepository services,
                               StaffRepository staff, EntityManager em) {
        this.appointments = appointments;
        this.services = services;
        this.staff = staff;
        this.em = em;
    }

    @Transactional(readOnly = true)
    public List<Slot> freeSlots(UUID tenantId, String serviceName, LocalDate date,
                                ZoneId zone, int limit) {
        ServiceOffering offering = services.findByTenantIdAndName(tenantId, serviceName)
                .orElseThrow(() -> new BookingService.UnknownServiceException(serviceName));
        List<StaffMember> candidates = offering.getStaff().stream()
                .filter(StaffMember::isActive).toList();
        if (candidates.isEmpty()) {
            candidates = staff.findByTenantIdAndActiveTrue(tenantId);
        }

        Instant dayStart = date.atStartOfDay(zone).toInstant();
        Instant dayEnd = date.plusDays(1).atStartOfDay(zone).toInstant();
        List<Appointment> booked = appointments.findConfirmedBetween(tenantId, dayStart, dayEnd);

        Set<String> taken = new HashSet<>();
        for (Appointment a : booked) {
            LocalTime t = a.getStartsAt().atZone(zone).toLocalTime();
            taken.add(a.getStaffId() + "@" + t);
        }

        List<Slot> out = new ArrayList<>();
        int step = Math.max(15, offering.getDurationMin());
        LocalTime now = LocalTime.now(zone);
        boolean today = date.equals(LocalDate.now(zone));

        for (StaffMember member : candidates) {
            Hours hours = hoursFor(tenantId, member.getId(), date.getDayOfWeek());
            if (hours == null) {
                continue;
            }
            for (int minute = hours.openMin();
                 minute + offering.getDurationMin() <= hours.closeMin(); minute += step) {
                if (hours.breakStart() != null
                        && minute >= hours.breakStart() && minute < hours.breakEnd()) {
                    continue;
                }
                LocalTime slot = LocalTime.of(minute / 60, minute % 60);
                if (today && slot.isBefore(now.plusMinutes(30))) {
                    continue;
                }
                if (taken.contains(member.getId() + "@" + slot)) {
                    continue;
                }
                out.add(new Slot(date, slot, member.getId(), member.getName()));
                if (out.size() >= limit) {
                    return out;
                }
            }
        }
        out.sort(Comparator.comparing(Slot::time));
        return out.size() > limit ? out.subList(0, limit) : out;
    }

    @Transactional(readOnly = true)
    public boolean isWithinWorkingHours(UUID tenantId, UUID staffId, LocalDate date,
                                        LocalTime time, int durationMin) {
        Hours hours = hoursFor(tenantId, staffId, date.getDayOfWeek());
        if (hours == null) {
            return false;
        }
        int start = time.getHour() * 60 + time.getMinute();
        return start >= hours.openMin() && start + durationMin <= hours.closeMin();
    }

    /** Staff-specific hours if present, otherwise the business-wide row. */
    private Hours hoursFor(UUID tenantId, UUID staffId, DayOfWeek day) {
        int weekday = day.getValue() - 1;
        Object[] row = (Object[]) em.createNativeQuery("""
                        SELECT open_min, close_min, break_start, break_end
                        FROM working_hours
                        WHERE tenant_id = :tenant AND weekday = :weekday
                          AND (staff_id = :staff OR staff_id IS NULL)
                        ORDER BY staff_id NULLS LAST LIMIT 1
                        """)
                .setParameter("tenant", tenantId)
                .setParameter("weekday", weekday)
                .setParameter("staff", staffId)
                .getResultStream().findFirst().orElse(null);
        if (row == null) {
            return null;
        }
        return new Hours(((Number) row[0]).intValue(), ((Number) row[1]).intValue(),
                row[2] == null ? null : ((Number) row[2]).intValue(),
                row[3] == null ? null : ((Number) row[3]).intValue());
    }
}
