package ai.haanji.core;

import ai.haanji.core.pramaan.CanonicalJson;
import ai.haanji.core.pramaan.ConfirmationProof;
import org.junit.jupiter.api.Test;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class LedgerServiceTest {

    @Test
    void canonicalJsonDoesNotDependOnInsertionOrder() {
        Map<String, Object> a = new LinkedHashMap<>();
        a.put("b", 1);
        a.put("a", List.of(1, Map.of("d", 2, "c", 3)));
        Map<String, Object> b = new LinkedHashMap<>();
        b.put("a", List.of(1, Map.of("c", 3, "d", 2)));
        b.put("b", 1);
        assertEquals(CanonicalJson.encode(a), CanonicalJson.encode(b));
    }

    @Test
    void canonicalJsonHasNoIncidentalWhitespace() {
        assertFalse(CanonicalJson.encode(Map.of("a", 1, "b", 2)).contains(" "));
    }

    @Test
    void aProofMustQuoteBothSidesOfTheExchange() {
        assertThrows(IllegalArgumentException.class,
                () -> new ConfirmationProof("", 0, "haan", 10, 0.9, 10));
        assertThrows(IllegalArgumentException.class,
                () -> new ConfirmationProof("Confirm kar dun?", 0, " ", 10, 0.9, 10));
    }

    @Test
    void aConfidenceOutsideZeroToOneIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> new ConfirmationProof("q", 0, "haan", 10, 1.4, 10));
    }

    @Test
    void aReplyThatPrecedesTheQuestionIsNotPlausible() {
        ConfirmationProof impossible =
                new ConfirmationProof("Confirm kar dun?", 5_000, "haan", 1_000, 0.9, -4_000);
        assertFalse(impossible.isPlausible());
    }

    @Test
    void anOrdinaryProofIsPlausible() {
        ConfirmationProof ok =
                new ConfirmationProof("Confirm kar dun?", 1_000, "haan ji", 4_200, 0.94, 3_200);
        assertTrue(ok.isPlausible());
    }
}
