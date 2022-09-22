from dataclasses import dataclass
import os
import sys
import glob
import subprocess

@dataclass
class TestSpec:
    """A collver Test Specification, containing input and expected outputs"""
    spec_path: str
    file_path: str
    compiler_stderr: bytes
    provided_input: str
    expected_stdout: bytes
    expected_stderr: bytes

@dataclass
class TestResult:
    """The result of a collver test, with the actual values"""
    test_spec: TestSpec
    compiler_stderr: bytes
    compile_success: bool
    actual_stdout: bytes
    actual_stderr: bytes


def eat_chunk(rlines: list[str]) -> str:
    """Eat a chunk of lines until the next [!MARKER]"""
    out = ""
    if len(rlines):
        line = rlines.pop()
    else:
        return out

    while len(rlines) and not line.startswith("[!"):
        out += line
        line = rlines.pop()

    if line.startswith("[!"):
        rlines.append(line)
    else:
        out += line

    return out

def parse_spec(spec_path: str) -> TestSpec:
    """Parse a test spec file into a text spec object"""
    spec = TestSpec(spec_path, "", b"", "", b"", b"")
    with open(spec_path, "r") as f:
        lines = f.readlines()

    rlines = list(reversed(lines))
    spec_basename = os.path.splitext(spec_path)[0]
    collver_file_path = spec_basename + ".collver"
    spec.file_path = collver_file_path
    while len(rlines):
        line = rlines.pop()
        if line == "[!COMERR]\n":
            spec.compiler_stderr = eat_chunk(rlines).encode("utf-8")
        elif line == "[!STDIN]\n":
            spec.provided_input = eat_chunk(rlines)
        elif line == "[!STDOUT]\n":
            spec.expected_stdout = eat_chunk(rlines).encode("utf-8")
        elif line == "[!STDERR]\n":
            spec.expected_stderr = eat_chunk(rlines).encode("utf-8")

    return spec

def run_echoed(cmd: list[str], print_outs: bool=False):
    print(f"<CMD> {' '.join(cmd)}")
    run_res = subprocess.run(cmd, capture_output=True)
    if print_outs:
        out = run_res.stdout.decode("utf-8")
        err = run_res.stderr.decode("utf-8")
        print(f"=> STDOUT:\n"+ out)
        print(f"=> STDERR:\n"+ err)

    return run_res

def run_spec(spec: TestSpec) -> TestResult:
    com_res = run_echoed(["python3.10", "collver.py", "to-ll", spec.file_path])
    if com_res.returncode != 0:
        return TestResult(spec, com_res.stderr, False, b"", b"")
    ll_path = os.path.splitext(spec.file_path)[0] + ".ll"
    run_echoed(["python3.10", "collver.py", "from-ll", ll_path])
    bin_path = os.path.splitext(spec.file_path)[0]
    run_res = run_echoed([bin_path])
    return TestResult(spec, com_res.stderr, True, run_res.stdout, run_res.stderr)

@dataclass
class Problem:
    """A problem (failed test)"""
    specpath: str # Path to the specfile
    field: str    # Name of what didn't match
    expected: str # What was expected
    actual: str   # The actual value

def print_problem(prob: Problem):
    print(f"Spec {prob.specpath}: {prob.field} didn't match!")
    print(f">> Expected:\n"+ prob.expected)
    print(f">> Actual:\n"+ prob.actual)


def check_match(sn: str, fieldname: str, expected: str, actual: str) -> list[Problem]:
    if expected != actual:
        return [
            Problem(
                sn,
                f"`{fieldname}`",
                expected,
                actual,
            )
        ]

    return []


def test_output(res: TestResult) -> list[Problem]:
    probs: list[Problem] = []
    basename = os.path.basename(res.test_spec.spec_path)
    # -- Compiler stderr --
    probs.extend(
        check_match(
            basename,
            "Compiler stderr",
            res.test_spec.compiler_stderr.decode("utf-8"),
            res.compiler_stderr.decode("utf-8"),
        )
    )

    if not res.compile_success:
        return probs # Don't bother to check the binary run results if the compile failed

    probs.extend(
        check_match(
            basename,
            "File stdout",
            res.test_spec.expected_stdout.decode("utf-8"),
            res.actual_stdout.decode("utf-8"),
        )
    )

    probs.extend(
        check_match(
            basename,
            "File stderr",
            res.test_spec.expected_stderr.decode("utf-8"),
            res.actual_stderr.decode("utf-8"),
        )
    )

    return probs

def test_specfile(fp: str) -> list[Problem]:
    spec = parse_spec(fp)
    res = run_spec(spec)
    probs = test_output(res)
    return probs

def find_specfiles(subfolder: str) -> list[str]:
    """Find specfiles in the ./tests/<folder>/ folder"""
    path = os.path.join("./tests", subfolder, "*.cts")
    specs = [str(g) for g in glob.glob(path)]
    return specs

def clean_spec(spec: str, quiet=False):
    """Delete byproducts (results of compilation) of a spec, given the path"""
    print(f"<INFO> Cleaning byproducts of spec `{spec}`")
    bin_path = os.path.splitext(spec)[0]
    ll_path = bin_path + ".ll"
    s_path = bin_path + ".s"
    if os.path.exists(bin_path) or os.path.exists(ll_path) or os.path.exists(s_path):
        if os.path.exists(ll_path):
            if not quiet:
                print(f"<rm> {ll_path}")
            os.remove(ll_path)
        if os.path.exists(s_path):
            if not quiet:
                print(f"<rm> {s_path}")
            os.remove(s_path)
        if os.path.exists(bin_path):
            if not quiet:
                print(f"<rm> {bin_path}")
            os.remove(bin_path)
    elif not quiet:
        print(f"No byproducts found")

def main():
    if len(sys.argv) < 2:
        print("Usage:\n  $ python3.10 test.py {all|std|builtin|clean} [-clean]\n")
        sys.exit(1)
    subcommand = sys.argv[1]
    match subcommand:
        case "all" | "std" | "builtin":
            if subcommand == "all":
                specs = find_specfiles("builtin")
                specs.extend(find_specfiles("std"))
            else:
                specs = find_specfiles(subcommand)
            print(f"==> Found {len(specs)} spec(s)")
            probs = []
            for spec in specs:
                print(f"<INFO> Testing spec `{spec}`")
                probs.extend(test_specfile(spec))
                if "-clean" in sys.argv:
                    clean_spec(spec, quiet=True)

            print(f"==> {len(specs)} spec(s) tested; {len(probs)} failed")
            for prob in probs:
                print_problem(prob)
        case "clean":
            specs = find_specfiles("builtin")
            specs.extend(find_specfiles("std"))
            for spec in specs:
                clean_spec(spec)
        case _:
            print(f"ERROR: Unknown subcommand `{subcommand}`")
            sys.exit(1)

if __name__ == '__main__':
    main()
