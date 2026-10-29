package ai.haanji.core.pramaan;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "haanji.ledger")
public record LedgerProperties(boolean requireConfirmation, String anchorCron) {
    public LedgerProperties {
        if (anchorCron == null || anchorCron.isBlank()) {
            anchorCron = "0 15 0 * * *";
        }
    }
}
