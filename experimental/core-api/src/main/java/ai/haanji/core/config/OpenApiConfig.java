package ai.haanji.core.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    OpenAPI haanjiOpenApi() {
        return new OpenAPI()
                .info(new Info()
                        .title("Haanji Core API")
                        .version("0.3.0")
                        .description("""
                                Control plane for the Haanji voice receptionist.

                                Two properties of this API are worth reading before using it.
                                Availability is a pure read and is safe to call speculatively.
                                Booking and cancellation require a confirmation proof in the
                                request body and will be refused without one, so a caller's
                                commitment can always be traced back to the words that made it.
                                """)
                        .contact(new Contact().name("Haanji").url("https://haanji.ai"))
                        .license(new License().name("Apache-2.0")))
                .schemaRequirement("bearer", new SecurityScheme()
                        .type(SecurityScheme.Type.HTTP).scheme("bearer").bearerFormat("JWT"))
                .addSecurityItem(new SecurityRequirement().addList("bearer"));
    }
}
