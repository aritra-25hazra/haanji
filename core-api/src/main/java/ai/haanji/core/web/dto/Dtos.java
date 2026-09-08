package ai.haanji.core.web.dto;

import jakarta.validation.constraints.*;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Wire types. Kept separate from the domain so the API can stay stable while
 *  the model moves, and so no entity is ever serialised by accident. */
public final class Dtos {
    private Dtos() { }

    public record SlotView(LocalDate date, LocalTime time, String staff, String spoken) { }

    public record AvailabilityResponse(String service, LocalDate date, boolean closed,
                                       List<SlotView> slots) { }

    public record ProofRequest(
            @NotBlank String promptText,
            long promptStartMs,
            @NotBlank String replyText,
            long replyStartMs,
            @DecimalMin("0.0") @DecimalMax("1.0") double asrConfidence,
            long audioOffsetMs) { }

    public record BookRequest(
            @NotBlank String service,
            @NotNull LocalDate date,
            @NotNull LocalTime time,
            String staff,
            String customerName,
            @Pattern(regexp = "\\d{10}", message = "phone must be ten digits") String phone,
            UUID conversationId,
            @NotNull @Valid ProofRequest confirmation,
            @NotBlank String transcriptExcerpt,
            @Positive int agentConfigVersion) { }

    public record BookResponse(UUID appointmentId, String receiptCode, String service,
                               String staff, Instant startsAt) { }

    public record CancelRequest(
            @NotNull UUID appointmentId,
            UUID conversationId,
            @NotNull @Valid ProofRequest confirmation,
            @NotBlank String transcriptExcerpt,
            @Positive int agentConfigVersion) { }

    public record LeadRequest(String name,
                              @Pattern(regexp = "\\d{10}") String phone,
                              @NotBlank String intent,
                              String note,
                              UUID conversationId) { }

    public record ReceiptView(long seq, String shortCode, String action,
                              Map<String, Object> actionArgs,
                              Map<String, Object> confirmation,
                              String transcriptExcerpt, Instant occurredAt,
                              String chainHash, String keyId) { }

    public record VerificationResponse(boolean ok, int checked, Long firstBrokenSeq,
                                       String reason, List<Long> missingSeqs,
                                       String publicKey) { }

    public record ConversationView(UUID conversationId, String channel, String callerPhone,
                                   Instant startedAt, Instant endedAt, String outcome,
                                   Integer durationMs, List<TurnView> turns,
                                   List<ReceiptView> receipts) { }

    public record TurnView(int seq, String speaker, String text, String rawText,
                           List<Map<String, Object>> corrections,
                           List<String> toolCalls, Integer latencyMs, boolean interrupted) { }

    public record DashboardResponse(long callsToday, long bookingsToday, long leadsOpen,
                                    double answerRate, double bookingRate,
                                    Map<String, Long> outcomes,
                                    Map<String, Double> latency,
                                    long correctionsToday, double speculationHitRate) { }

    public record ErrorResponse(String error, String message, Instant at) {
        public static ErrorResponse of(String error, String message) {
            return new ErrorResponse(error, message, Instant.now());
        }
    }
}
