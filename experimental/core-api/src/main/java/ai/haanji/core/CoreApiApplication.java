package ai.haanji.core;

import ai.haanji.core.repo.Repositories;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
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
// The repository interfaces are nested inside Repositories on purpose;
// Spring Data does not scan nested interfaces unless told to.
@EnableJpaRepositories(basePackageClasses = Repositories.class,
        considerNestedRepositories = true)
public class CoreApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(CoreApiApplication.class, args);
    }
}
