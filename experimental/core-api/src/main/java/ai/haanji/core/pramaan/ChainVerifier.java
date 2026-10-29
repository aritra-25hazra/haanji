package ai.haanji.core.pramaan;

import ai.haanji.core.domain.Receipt;
import org.bouncycastle.crypto.params.Ed25519PublicKeyParameters;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.util.*;

/**
 * Re-derives every hash and checks every signature in a tenant's chain.
 *
 * <p>Deliberately small and free of clever abstractions: an auditor should be
 * able to read this class in one sitting and satisfy themselves that it does
 * not trust anything the platform stored except the receipts themselves.
 */
@Component
public class ChainVerifier {

    public record Result(boolean ok, int checked, Long firstBrokenSeq,
                         String reason, List<Long> missingSeqs) {

        public static Result valid(int checked) {
            return new Result(true, checked, null, null, List.of());
        }

        @Override
        public String toString() {
            return ok ? "VALID - " + checked + " receipts, chain intact"
                      : "BROKEN at seq " + firstBrokenSeq + ": " + reason;
        }
    }

    private static final byte[] GENESIS = new byte[32];

    private final SigningKeyStore keys;

    public ChainVerifier(SigningKeyStore keys) {
        this.keys = keys;
    }

    public Result verify(List<Receipt> receipts, Ed25519PublicKeyParameters publicKey) {
        if (receipts.isEmpty()) {
            return Result.valid(0);
        }
        List<Receipt> ordered = receipts.stream()
                .sorted(Comparator.comparingLong(Receipt::getSeq)).toList();

        Set<Long> present = new HashSet<>();
        ordered.forEach(r -> present.add(r.getSeq()));
        List<Long> missing = new ArrayList<>();
        for (long s = ordered.getFirst().getSeq(); s <= ordered.getLast().getSeq(); s++) {
            if (!present.contains(s)) {
                missing.add(s);
            }
        }

        byte[] prev = ordered.getFirst().getSeq() == 1 ? GENESIS : ordered.getFirst().getPrevHash();
        int checked = 0;
        for (Receipt r : ordered) {
            if (!Arrays.equals(r.getPrevHash(), prev)) {
                return new Result(false, checked, r.getSeq(),
                        "prev_hash does not match the previous receipt's chain hash", missing);
            }
            String reason = verifyOne(r, publicKey);
            if (reason != null) {
                return new Result(false, checked, r.getSeq(), reason, missing);
            }
            prev = r.getChainHash();
            checked++;
        }
        if (!missing.isEmpty()) {
            return new Result(false, checked, missing.getFirst(),
                    "sequence gap - a receipt was deleted", missing);
        }
        return Result.valid(checked);
    }

    /** @return null when the receipt is sound, otherwise why it is not. */
    public String verifyOne(Receipt r, Ed25519PublicKeyParameters publicKey) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("action", r.getAction());
        payload.put("action_args", r.getActionArgs());
        payload.put("confirmation", r.getConfirmation());
        payload.put("transcript_excerpt", r.getTranscriptExcerpt());
        payload.put("occurred_at", r.getOccurredAt().toString());
        payload.put("agent_config_version", r.getAgentConfigVersion());

        byte[] payloadHash = LedgerService.sha256(
                CanonicalJson.encode(payload).getBytes(StandardCharsets.UTF_8));
        if (!Arrays.equals(payloadHash, r.getPayloadHash())) {
            return "payload hash does not match the stored content";
        }
        byte[] chainHash = LedgerService.sha256(
                LedgerService.concat(r.getPrevHash(), r.getPayloadHash()));
        if (!Arrays.equals(chainHash, r.getChainHash())) {
            return "chain hash does not match prev_hash + payload_hash";
        }
        if (!keys.verify(publicKey, r.getChainHash(), r.getSignature())) {
            return "signature does not verify against the tenant public key";
        }
        return null;
    }

    /** Merkle root over a day's chain hashes, for the daily anchor. */
    public byte[] merkleRoot(List<Receipt> ordered) {
        if (ordered.isEmpty()) {
            return GENESIS;
        }
        List<byte[]> level = new ArrayList<>(ordered.stream().map(Receipt::getChainHash).toList());
        while (level.size() > 1) {
            List<byte[]> next = new ArrayList<>();
            for (int i = 0; i < level.size(); i += 2) {
                byte[] left = level.get(i);
                byte[] right = (i + 1 < level.size()) ? level.get(i + 1) : left;
                next.add(LedgerService.sha256(LedgerService.concat(left, right)));
            }
            level = next;
        }
        return level.getFirst();
    }
}
