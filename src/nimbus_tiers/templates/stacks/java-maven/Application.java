package com.example.{{PACKAGE_NAME}};

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class {{CLASS_NAME}}Application {

    public static void main(String[] args) {
        SpringApplication.run({{CLASS_NAME}}Application.class, args);
    }

    @Bean
    CommandLineRunner run() {
        return args -> System.out.println(greet());
    }

    public static String greet() {
        return "Hello, World!";
    }
}
