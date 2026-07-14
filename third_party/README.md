# Third-party dependencies

Do not copy dependencies here by default. GoogleTest is fetched by CMake at a pinned commit
for test builds. Vendoring is reserved for dependencies that require auditing, patching,
offline builds, or a documented reproducibility guarantee beyond a pinned source revision.
