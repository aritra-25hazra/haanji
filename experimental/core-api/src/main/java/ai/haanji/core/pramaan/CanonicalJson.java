package ai.haanji.core.pramaan;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * A single, byte-stable serialisation of a receipt's payload.
 *
 * <p>The hash of a receipt has to be reproducible years later by an auditor
 * using a different language, so the encoding cannot depend on map ordering,
 * whitespace or floating point formatting. Keys are sorted, separators are
 * fixed, and numbers are emitted in their shortest exact form.
 */
public final class CanonicalJson {

    private static final ObjectMapper MAPPER = new ObjectMapper()
            .disable(SerializationFeature.INDENT_OUTPUT)
            .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);

    private CanonicalJson() { }

    public static String encode(Object value) {
        try {
            return MAPPER.writeValueAsString(normalise(value));
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("value is not canonicalisable", e);
        }
    }

    @SuppressWarnings("unchecked")
    private static Object normalise(Object value) {
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> sorted = new TreeMap<>();
            map.forEach((k, v) -> sorted.put(String.valueOf(k), normalise(v)));
            return sorted;
        }
        if (value instanceof List<?> list) {
            return list.stream().map(CanonicalJson::normalise).toList();
        }
        if (value instanceof Double d) {
            return BigDecimal.valueOf(d).stripTrailingZeros();
        }
        if (value instanceof Float f) {
            return BigDecimal.valueOf(f.doubleValue()).stripTrailingZeros();
        }
        return value;
    }
}
