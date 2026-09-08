package ai.haanji.core;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.transaction.annotation.EnableTransactionManagement;

/**
 * The Haanji control plane.
 *
 * <p>Everything that must survive a restart lives behind this service: tenants,
 * catalogues, calendars, conversations and the Pramaan ledger. The voice engine
 * is deliberately stateless and calls in here for anything it needs to remember,
 * which is what lets a call be picked up by a different engine process if one
 * dies mid-conversation.
 */
@SpringBootApplication
@ConfigurationPropertiesScan
@EnableTransactionManagement
@EnableScheduling
public class CoreApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(CoreApiApplication.class, args);
    }
}
