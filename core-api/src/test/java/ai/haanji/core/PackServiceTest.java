package ai.haanji.core;

import ai.haanji.core.packs.PackService;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PackServiceTest {

    @Test
    void aDayRangeExpands() {
        assertEquals(List.of(0, 1, 2, 3, 4, 5), PackService.expandDays("mon-sat"));
    }

    @Test
    void aRangeMayWrapAroundTheWeek() {
        assertEquals(List.of(5, 6, 0), PackService.expandDays("sat-mon"));
    }

    @Test
    void singleDaysAndListsWork() {
        assertEquals(List.of(6), PackService.expandDays("sun"));
        assertEquals(List.of(0, 4), PackService.expandDays("mon,fri"));
    }

    @Test
    void timesBecomeMinutesPastMidnight() {
        assertEquals(570, PackService.minutes("09:30"));
        assertEquals(1200, PackService.minutes("20:00"));
    }
}
