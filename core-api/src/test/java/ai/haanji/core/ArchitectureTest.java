package ai.haanji.core;

import com.tngtech.archunit.base.DescribedPredicate;
import com.tngtech.archunit.core.domain.JavaClass;
import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.domain.JavaMethod;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.lang.ArchCondition;
import com.tngtech.archunit.lang.ArchRule;
import com.tngtech.archunit.lang.ConditionEvents;
import com.tngtech.archunit.lang.SimpleConditionEvent;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.*;
import static com.tngtech.archunit.library.Architectures.layeredArchitecture;

/**
 * Rules that survive the people who wrote them.
 *
 * <p>Every one of these encodes a decision from the design document. Writing
 * them as tests means the decision is enforced on every commit instead of
 * being remembered in a review.
 */
class ArchitectureTest {

    private static JavaClasses classes;

    @BeforeAll
    static void load() {
        classes = new ClassFileImporter()
                .withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TESTS)
                .importPackages("ai.haanji.core");
    }

    @Test
    void layersAreRespected() {
        layeredArchitecture().consideringOnlyDependenciesInLayers()
                .layer("Web").definedBy("ai.haanji.core.web..")
                .layer("Service").definedBy("ai.haanji.core.service..", "ai.haanji.core.packs..")
                .layer("Pramaan").definedBy("ai.haanji.core.pramaan..")
                .layer("Repository").definedBy("ai.haanji.core.repo..")
                .layer("Domain").definedBy("ai.haanji.core.domain..")
                .whereLayer("Web").mayNotBeAccessedByAnyLayer()
                .whereLayer("Service").mayOnlyBeAccessedByLayers("Web")
                .whereLayer("Repository").mayOnlyBeAccessedByLayers("Web", "Service", "Pramaan")
                .check(classes);
    }

    @Test
    void controllersNeverTouchRepositoriesDirectlyForWrites() {
        noClasses().that().resideInAPackage("..web..")
                .should().callMethodWhere(DescribedPredicate.describe(
                        "a save method on a repository", target ->
                        target.getTarget().getOwner().getName().contains(".repo.")
                                && target.getTarget().getName().startsWith("save")))
                .because("a write must go through a service so it is sealed in the ledger")
                .check(classes);
    }

    @Test
    void entitiesAreNeverReturnedFromControllers() {
        methods().that().areDeclaredInClassesThat().resideInAPackage("..web..")
                .should(notReturnAnEntity())
                .because("a controller returns a DTO, so the wire format does not have "
                         + "to change every time an entity does")
                .check(classes);
    }

    /**
     * Looks at every raw type involved in the return signature rather than just
     * the outermost one, so {@code ResponseEntity<List<Receipt>>} is caught as
     * surely as a bare {@code Receipt}.
     */
    private static ArchCondition<JavaMethod> notReturnAnEntity() {
        return new ArchCondition<JavaMethod>("not return a class from ..domain..") {
            @Override
            public void check(JavaMethod method, ConditionEvents events) {
                boolean clean = true;
                for (JavaClass involved : method.getReturnType().getAllInvolvedRawTypes()) {
                    if (involved.getPackageName().startsWith("ai.haanji.core.domain")) {
                        clean = false;
                        events.add(SimpleConditionEvent.violated(method,
                                method.getFullName() + " returns the entity "
                                        + involved.getSimpleName()));
                    }
                }
                if (clean) {
                    events.add(SimpleConditionEvent.satisfied(method,
                            method.getFullName() + " returns a DTO"));
                }
            }
        };
    }

    @Test
    void receiptsAreImmutable() {
        ArchRule rule = noMethods().that().areDeclaredInClassesThat()
                .haveSimpleName("Receipt")
                .should().haveNameStartingWith("set")
                .because("a receipt is written once and read forever");
        rule.check(classes);
    }

    @Test
    void noFieldInjection() {
        noFields().should().beAnnotatedWith("org.springframework.beans.factory.annotation.Autowired")
                .because("constructor injection makes dependencies visible and testable")
                .check(classes);
    }

    @Test
    void noSystemOut() {
        noClasses().should().accessField(System.class, "out")
                .orShould().accessField(System.class, "err")
                .because("logs go through SLF4J so they can be shipped and filtered")
                .check(classes);
    }
}
