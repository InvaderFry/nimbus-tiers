package com.example.{{PACKAGE_NAME}};

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class {{CLASS_NAME}}ApplicationTest {

    @Test
    void contextLoads() {
    }

    @Test
    void greetReturnsHelloWorld() {
        assertThat({{CLASS_NAME}}Application.greet()).isEqualTo("Hello, World!");
    }
}
