package ai.haanji.core.web;

import ai.haanji.core.domain.Conversation;
import ai.haanji.core.repo.Repositories.ConversationRepository;
import ai.haanji.core.repo.Repositories.ReceiptRepository;
import ai.haanji.core.service.TenantContext;
import ai.haanji.core.web.dto.Dtos.*;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.persistence.EntityManager;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/conversations")
@Tag(name = "Conversations", description = "Call history and transcripts")
public class ConversationController {

    private final ConversationRepository conversations;
    private final ReceiptRepository receipts;
    private final EntityManager em;

    public ConversationController(ConversationRepository conversations,
                                  ReceiptRepository receipts, EntityManager em) {
        this.conversations = conversations;
        this.receipts = receipts;
        this.em = em;
    }

    @GetMapping
    @Operation(summary = "The 50 most recent calls")
    public List<Map<String, Object>> recent() {
        return conversations.findTop50ByTenantIdOrderByStartedAtDesc(TenantContext.require())
                .stream().map(c -> Map.<String, Object>of(
                        "conversation_id", c.getId(),
                        "channel", c.getChannel().name(),
                        "caller_phone", mask(c.getCallerPhone()),
                        "started_at", c.getStartedAt(),
                        "outcome", c.getOutcome() == null ? "IN_PROGRESS" : c.getOutcome().name(),
                        "duration_ms", c.getDurationMs() == null ? 0 : c.getDurationMs()))
                .toList();
    }

    @GetMapping("/{id}")
    @Operation(summary = "One call with its transcript, corrections and receipts")
    @SuppressWarnings("unchecked")
    public ConversationView detail(@PathVariable UUID id) {
        UUID tenantId = TenantContext.require();
        Conversation c = conversations.findById(id)
                .filter(x -> x.getTenantId().equals(tenantId))
                .orElseThrow(() -> new IllegalArgumentException("no conversation " + id));

        List<Object[]> rows = em.createNativeQuery("""
                        SELECT seq, speaker, text, raw_text, corrections, tool_calls,
                               latency_ms, interrupted
                        FROM turns WHERE conversation_id = :id ORDER BY seq
                        """)
                .setParameter("id", id)
                .getResultList();

        List<TurnView> turns = rows.stream().map(r -> new TurnView(
                ((Number) r[0]).intValue(), (String) r[1], (String) r[2], (String) r[3],
                List.of(), List.of(),
                r[6] == null ? null : ((Number) r[6]).intValue(),
                Boolean.TRUE.equals(r[7]))).toList();

        return new ConversationView(c.getId(), c.getChannel().name(), mask(c.getCallerPhone()),
                c.getStartedAt(), c.getEndedAt(),
                c.getOutcome() == null ? "IN_PROGRESS" : c.getOutcome().name(),
                c.getDurationMs(), turns,
                receipts.findByConversationIdOrderBySeqAsc(id).stream()
                        .map(r -> new ReceiptView(r.getSeq(), r.getShortCode(), r.getAction(),
                                r.getActionArgs(), r.getConfirmation(), r.getTranscriptExcerpt(),
                                r.getOccurredAt(), "", r.getKeyId())).toList());
    }

    /** Console users see enough of a number to recognise a caller, not enough
     *  to export a marketing list. */
    private static String mask(String phone) {
        if (phone == null || phone.length() < 6) {
            return phone;
        }
        return phone.substring(0, 2) + "XXXXXX" + phone.substring(phone.length() - 2);
    }
}
