package ai.haanji.core.web;

import java.time.LocalTime;
import java.util.Map;

/** How a receptionist would read a time out loud. The API returns both the
 *  machine form and this one, so the engine never has to invent phrasing. */
final class SpokenTime {

    private static final Map<Integer, String> HALVES =
            Map.of(30, "saade ", 15, "sava ", 45, "paune ");

    private SpokenTime() { }

    static String of(LocalTime time) {
        int h = time.getHour();
        int m = time.getMinute();
        String part = h < 12 ? "subah" : (h < 16 ? "dopahar" : "shaam");
        int h12 = (h >= 1 && h <= 12) ? h : (h % 12 == 0 ? 12 : h % 12);
        if (m == 45) {
            h12 = h12 % 12 + 1;
        }
        String prefix = HALVES.getOrDefault(m, "");
        String minutes = (HALVES.containsKey(m) || m == 0) ? "" : String.format(":%02d", m);
        return part + " " + prefix + h12 + minutes + " baje";
    }
}
