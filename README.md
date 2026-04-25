# Lillorepo 👾

Our monorepo of projects and experiments.

## What is this?

This is a **monorepo** — a centralised place where we store and manage all our software projects. The idea is simple: instead of having many small, scattered repositories, we have a single, large, well-organised one.

This lets us share common code easily, keep dependencies under control, and have a global view of everything we are building.

## Repository Structure

Organisation is key. The main structure you will find is:

-   `📁 /core`: Our shared toolbox. All the logic, API clients, and utilities that can be reused by any project in the repo live here. If something is going to be used more than once, it probably belongs here.

-   `📁 /packages`: The heart of lillorepo. Each of our main projects lives inside this folder, grouped in their own directories. Each subdirectory is its own universe, but all share the tools from `core`.

## 🛠️ Built with Bazel

Everything here is managed with **Bazel**, a build system that lets us handle dependencies between packages efficiently and guarantees fast, reproducible builds.
