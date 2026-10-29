package ai.haanji.core.web;

import ai.haanji.core.domain.Appointment;
import ai.haanji.core.pramaan.ConfirmationProof;
import ai.haanji.core.service.AvailabilityService;
import ai.haanji.core.service.BookingService;
import ai.haanji.core.service.TenantContext;
import ai.haanji.core.web.dto.Dtos.*;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import java.util.UUID;

/**
 * The endpoints the voice engine calls during a live conversation.
 *
 * <p>{@code /availability} is a pure read and is the one the engine is allowed
 * to speculate on. {@code /book} and {@code /cancel} both demand a confirmation
 * proof in the request body — the API makes it impossible to write without one,
 * so the guarantee does not depend on the engine behaving well.
 */
@RestController
@RequestMapping("/api/v1/booking")
@Tag(name = "Booking", description = "Slots, bookings and cancellations")
public class BookingController {

    private final AvailabilityService availability;
    private final BookingService bookings;
    private final ZoneId zone = ZoneId.of("Asia/Kolkata");

    public BookingController(AvailabilityService availability, BookingService bookings) {
        this.availability = availability;
        this.bookings = bookings;
    }

    @GetMapping("/availability")
    @Operation(summary = "Free slots for a service on a day (read-only, speculatable)")
    public AvailabilityResponse availability(@RequestParam String service,
                                             @RequestParam LocalDate date,
                                             @RequestParam(defaultValue = "3") int limit) {
        UUID tenantId = TenantContext.require();
        List<AvailabilityService.Slot> slots =
                availability.freeSlots(tenantId, service, date, zone, limit);
        return new AvailabilityResponse(service, date, slots.isEmpty(),
                slots.stream().map(s -> new SlotView(s.date(), s.time(), s.staffName(),
                        SpokenTime.of(s.time()))).toList());
    }

    @PostMapping("/book")
    @Operation(summary = "Create an appointment. Requires a confirmation proof.")
    public ResponseEntity<BookResponse> book(@Valid @RequestBody BookRequest request) {
        UUID tenantId = TenantContext.require();
        ConfirmationProof proof = toProof(request.confirmation());
        BookingService.BookingResult result = bookings.book(tenantId,
                new BookingService.BookingRequest(request.service(), request.date(),
                        request.time(), request.staff(), request.customerName(),
                        request.phone(), request.conversationId(), Appointment.Source.VOICE,
                        proof, request.transcriptExcerpt(), request.agentConfigVersion()),
                zone);
        return ResponseEntity.ok(new BookResponse(result.appointment().getId(),
                result.receiptCode(), result.serviceName(), result.staffName(),
                result.appointment().getStartsAt()));
    }

    @PostMapping("/cancel")
    @Operation(summary = "Cancel an appointment. Requires a confirmation proof.")
    public ResponseEntity<String> cancel(@Valid @RequestBody CancelRequest request) {
        UUID tenantId = TenantContext.require();
        String code = bookings.cancel(tenantId, request.appointmentId(),
                toProof(request.confirmation()), request.conversationId(),
                request.transcriptExcerpt(), request.agentConfigVersion());
        return ResponseEntity.ok(code);
    }

    private static ConfirmationProof toProof(ProofRequest p) {
        return new ConfirmationProof(p.promptText(), p.promptStartMs(), p.replyText(),
                p.replyStartMs(), p.asrConfidence(), p.audioOffsetMs());
    }
}
