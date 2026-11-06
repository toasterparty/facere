from pathlib import PurePosixPath

import facere as fac

PROGRAMS = [PurePosixPath(main).stem for main in fac.sources("apps/*.c")]
CJSON = "third_party/cjson"
CJSON_C = f"{CJSON}/cJSON.c"
CJSON_H = f"{CJSON}/cJSON.h"
WARNINGS = ["-Wall", "-Wextra", "-Wpedantic", "-Wshadow", "-Wconversion"]
SANITIZERS = ["-fsanitize=address,undefined"]


CONFIGURATIONS = {
    "debug": {
        "cflags": ["-O0", "-g3", "-fno-omit-frame-pointer"],
        "checks": WARNINGS,
        "ldflags": [],
    },
    "test": {
        "cflags": SANITIZERS + ["-fno-sanitize-recover=all", "-O1", "-g"],
        "checks": WARNINGS + ["-fanalyzer", "-Werror"],
        "ldflags": SANITIZERS,
    },
    "release": {
        "cflags": ["-O2", "-flto", "-DNDEBUG", "-ffunction-sections", "-fdata-sections"],
        "checks": WARNINGS,
        "ldflags": ["-O2", "-flto", "-Wl,--gc-sections", "-s"],
    },
}


@fac.rule
def cjson(files: list[fac.Output] = [CJSON_C, CJSON_H]):
    fac.fetch.archive(
        CJSON,
        url="https://github.com/DaveGamble/cJSON/archive/refs/tags/v1.7.18.tar.gz",
        sha256="3aa806844a03442c00769b83e99970be70fbef03735ff898f4811dd03b9f5ee5",
        strip_components=1,
    )


def toolchain(configuration):
    cflags = configuration["cflags"] + configuration["checks"] + ["-I.", "-isystem", CJSON]
    return fac.c.Toolchain(ar="gcc-ar", cflags=cflags, ldflags=configuration["ldflags"])


LIBRARIES = {}
with fac.scope("common"):
    for name, configuration in CONFIGURATIONS.items():
        with fac.scope(name):
            vendor = fac.c.Toolchain(ar="gcc-ar", cflags=configuration["cflags"])
            common_sources = fac.sources("src/common/**/*.c")
            LIBRARIES[name] = [
                toolchain(configuration).static_library("libcommon.a", common_sources, inputs=[CJSON_H]),
                vendor.static_library("libcjson.a", [CJSON_C]),
            ]

for program in PROGRAMS:
    with fac.scope(program, default=True):
        for name, configuration in CONFIGURATIONS.items():
            with fac.scope(name, default=(name == "debug")):
                program_sources = [f"apps/{program}.c"] + fac.sources(f"src/{program}/**/*.c")
                executable = toolchain(configuration).executable(program, program_sources, libraries=LIBRARIES[name], default=True)

                @fac.task
                def run(args: fac.Args, path: fac.Input = executable):
                    fac.run(path, args)

with fac.scope("tests"):
    for name, configuration in CONFIGURATIONS.items():
        with fac.scope(name, default=(name == "debug")):
            tests = toolchain(configuration).executables(fac.sources("tests/*.c"), libraries=LIBRARIES[name])

            @fac.task
            def run(programs: list[fac.Input] = tests):
                for program in programs:
                    fac.run(program, env={"UBSAN_OPTIONS": "print_stacktrace=1"})

fac.c.compile_commands(scope="*.debug", default=True)
