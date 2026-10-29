package ai.haanji.core.pramaan;

import ai.haanji.core.domain.Receipt;
import ai.haanji.core.repo.Repositories.ReceiptRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.*;

/**
 * Appends to the tenant's tamper-evident chain.
 *
 * <p>The write to the ledger and the write to the business table happen in the
 * same transaction. That is the whole point: it is impossible to end up with a
 * booking that has no receipt, or a receipt for a booking that was rolled back.
 */
@Service
public class LedgerService {

    private static final Logger log = LoggerFactory.getLogger(LedgerService.class);
    private static final byte[] GENESIS = new byte[32];

    private final ReceiptRepository receipts;
    private final SigningKeyStore keys;
    private final boolean requireConfirmation;

    public LedgerService(ReceiptRepository receipts, SigningKeyStore keys,
                         LedgerProperties properties) {
        this.receipts = receipts;
        this.keys = keys;
        this.requireConfirmation = properties.requireConfirmation();
    }

    /**
     * Seal one action.
     *
     * @param requiresConfirmation whether this action changes something the
     *        caller committed to. When it does and no proof is present, the
     *        append is refused, which fails the surrounding transaction and so
     *        prevents the business write as well.
     */
    @Transactional(propagation = Propagation.MANDATORY)
    public Receipt append(UUID tenantId, UUID conversationId, String action,
                          Map<String, Object> actionArgs, ConfirmationProof proof,
                          String transcriptExcerpt, int agentConfigVersion,
                          boolean requiresConfirmation) {

        if (requiresConfirmation && requireConfirmation && proof == null) {
            throw new UnconfirmedWriteException(action);
        }
        if (proof != null && !proof.isPlausible()) {
            throw new UnconfirmedWriteException(action + " (the reply precedes the question)");
        }

        SigningKeyStore.Key key = keys.activeKeyFor(tenantId);
        long seq = receipts.findMaxSeq(tenantId).orElse(0L) + 1;
        byte[] prevHash = seq == 1 ? GENESIS
                : receipts.findRange(tenantId, seq - 1, seq - 1).getFirst().getChainHash();

        Instant occurredAt = Instant.now();
        Map<String, Object> confirmation = proof == null ? Map.of() : proof.asMap();

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("action", action);
        payload.put("action_args", actionArgs);
        payload.put("confirmation", confirmation);
        payload.put("transcript_excerpt", transcriptExcerpt);
        payload.put("occurred_at", occurredAt.toString());
        payload.put("agent_config_version", agentConfigVersion);

        byte[] payloadHash = sha256(CanonicalJson.encode(payload).getBytes(StandardCharsets.UTF_8));
        byte[] chainHash = sha256(concat(prevHash, payloadHash));
        byte[] signature = keys.sign(key, chainHash);
        String shortCode = shortCode(chainHash);

        Receipt receipt = new Receipt(tenantId, seq, conversationId, action, actionArgs,
                confirmation, transcriptExcerpt, agentConfigVersion, occurredAt,
                prevHash, payloadHash, chainHash, signature, key.keyId(), shortCode);
        Receipt saved = receipts.save(receipt);
        log.info("sealed receipt seq={} action={} code={} tenant={}",
                seq, action, shortCode, tenantId);
        return saved;
    }

    /** A code short enough to read out on the phone, derived from the hash so
     *  it cannot be chosen. */
    static String shortCode(byte[] chainHash) {
        String hex = HexFormat.of().withUpperCase().formatHex(chainHash);
        return hex.substring(0, 4) + "-" + hex.substring(4, 8);
    }

    static byte[] sha256(byte[] input) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(input);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is required and missing", e);
        }
    }

    static byte[] concat(byte[] a, byte[] b) {
        byte[] out = Arrays.copyOf(a, a.length + b.length);
        System.arraycopy(b, 0, out, a.length, b.length);
        return out;
    }

    public static class UnconfirmedWriteException extends RuntimeException {
        public UnconfirmedWriteException(String action) {
            super("action '" + action + "' has no confirmation proof; the ledger "
                    + "refuses to record an unconfirmed write");
        }
    }
}
