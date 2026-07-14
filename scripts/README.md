# Development scripts

Run these commands from any directory; each script resolves the repository root itself.

| Script | Purpose |
| --- | --- |
| `./scripts/configure.sh` | Configure `build/` in Debug mode, or set `BUILD_TYPE`. |
| `./scripts/build.sh` | Configure and compile all enabled targets. |
| `./scripts/test.sh` | Configure, build, and run CTest with failure output. |
| `./scripts/format.sh` | Apply the checked-in clang-format policy. |
| `./scripts/check_format.sh` | Verify formatting without changing files. |

The formatter scripts require `clang-format` on `PATH`, or an explicit `CLANG_FORMAT`
executable. CMake's default `BUILD_TESTING=ON` downloads the pinned GoogleTest revision;
use `-DBUILD_TESTING=OFF` only for an offline application-only build.
