# acceptance-tampered

This fixture is a *valid* project (same Zener schematic as `valid-blinky`).
It exists so tests can copy it to a temporary directory, modify a protected
file in flight, and assert the harness detects the tamper via
`ProtectedHashes.verify()`.

Do not "fix" the fixture by editing the files here in ways that make
tamper-detection impossible. That defeats the purpose of the test.