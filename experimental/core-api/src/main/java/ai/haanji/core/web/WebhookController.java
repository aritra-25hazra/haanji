package ai.haanji.core.web;

import ai.haanji.core.domain.Conversation;
import ai.haanji.core.domain.Tenant;
import ai.haanji.core.repo.Repositories.TenantRepository;
import ai.haanji.core.service.ConversationService;
import ai.haanji.core.service.TenantContext;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;

/**
 * Inbound telephony and WhatsApp.
 *
 * <p>Two things matter here and nothing else does. The signature is checked
 * with a constant-time comparison before anything is parsed, and the tenant is
 * resolved from the number that was dialled rather than from anything in the
 * request body, so a forged payload cannot address another tenant.
 */
@RestController
@RequestMapping("/webhooks")
@Tag(name = "Webhooks", description = "Telephony and WhatsApp callbacks")
public class WebhookController {

    private static final Logger log = LoggerFactory.getLogger(WebhookController.class);

    private final TenantRepository tenants;
    private final ConversationService conversations;
    private final String secret;

    public WebhookController(TenantRepository tenants, ConversationService conversations,
                             @Value("${haanji.telephony.webhook-secret}") String secret) {
        this.tenants = tenants;
        this.conversations = conversations;
        this.secret = secret;
    }

    @PostMapping("/voice/incoming")
    @Operation(summary = "A call arrived on a tenant's number")
    public ResponseEntity<Map<String, Object>> incomingCall(
            @RequestHeader(value = "X-Haanji-Signature", required = false) String signature,
            @RequestBody Map<String, String> body) {

        String raw = body.getOrDefault("raw", "");
        if (!signatureMatches(raw, signature)) {
            log.warn("rejected a voice webhook with a bad signature");
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }
        String dialled = body.get("To");
        Tenant tenant = tenants.findByPhoneNumber(dialled).orElse(null);
        if (tenant == null || !tenant.isActive()) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).build();
        }
        TenantContext.set(tenant.getId());
        Conversation conversation = conversations.start(
                tenant.getId(), Conversation.Channel.PHONE, body.get("From"));

        return ResponseEntity.ok(Map.of(
                "conversation_id", conversation.getId(),
                "tenant_id", tenant.getId(),
                "pack_id", tenant.getPackId(),
                "pack_version", tenant.getPackVersion(),
                "greeting_locale", tenant.getTimezone(),
                "engine_ws", "/engine/v1/stream/" + conversation.getId()));
    }

    @PostMapping("/whatsapp/incoming")
    @Operation(summary = "A WhatsApp message arrived")
    public ResponseEntity<Map<String, Object>> incomingMessage(
            @RequestHeader(value = "X-Haanji-Signature", required = false) String signature,
            @RequestBody Map<String, String> body) {

        if (!signatureMatches(body.getOrDefault("raw", ""), signature)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }
        Tenant tenant = tenants.findByWhatsappNumber(body.get("to")).orElse(null);
        if (tenant == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).build();
        }
        TenantContext.set(tenant.getId());
        Conversation conversation = conversations.start(
                tenant.getId(), Conversation.Channel.WHATSAPP, body.get("from"));
        return ResponseEntity.ok(Map.of("conversation_id", conversation.getId()));
    }

    private boolean signatureMatches(String payload, String provided) {
        if (provided == null) {
            return false;
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            String expected = HexFormat.of()
                    .formatHex(mac.doFinal(payload.getBytes(StandardCharsets.UTF_8)));
            return MessageDigest.isEqual(expected.getBytes(StandardCharsets.UTF_8),
                    provided.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            return false;
        }
    }
}
