package ai.haanji.core.pramaan;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * The evidence that a caller agreed to a specific action.
 *
 * <p>It is not a boolean. It records the exact sentence the agent said, the
 * exact words the caller answered with, how long after the question the answer
 * began, and how sure the recogniser was — everything a person would need in
 * order to judge, months later, whether that "haan" really meant yes.
 */
public record ConfirmationProof(String promptText,
                                long promptStartMs,
                                String replyText,
                                long replyStartMs,
                                double asrConfidence,
                                long audioOffsetMs) {

    public ConfirmationProof {
        if (promptText == null || promptText.isBlank()) {
            throw new IllegalArgumentException("a proof must quote the question that was asked");
        }
        if (replyText == null || replyText.isBlank()) {
            throw new IllegalArgumentException("a proof must quote the caller's answer");
        }
        if (asrConfidence < 0 || asrConfidence > 1) {
            throw new IllegalArgumentException("asrConfidence must be a probability");
        }
    }

    public Map<String, Object> asMap() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("prompt_text", promptText);
        out.put("prompt_start_ms", promptStartMs);
        out.put("reply_text", replyText);
        out.put("reply_start_ms", replyStartMs);
        out.put("asr_confidence", asrConfidence);
        out.put("audio_offset_ms", audioOffsetMs);
        return out;
    }

    /** A reply that arrives before the question finished is not a reply to it. */
    public boolean isPlausible() {
        return audioOffsetMs >= 0 && replyStartMs >= promptStartMs;
    }
}
