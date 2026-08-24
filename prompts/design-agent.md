# Diode/Zener Design Agent Prompt

Design atau repair project Diode sebagai bounded engineering task.

1. Baca `AGENT_PROTOCOL.md` dan tiga contract JSON project.
2. Kaitkan setiap edit dengan requirement/acceptance ID.
3. Jalankan doctor; missing mandatory tool menjadi `BLOCKED`.
4. Edit hanya `src/**/*.zen`, kecuali user memberi explicit layout scope.
5. Gunakan Zener public syntax dari docs/toolchain lane project. Jangan mengarang
   module, pin, package, MPN, CLI flag, atau output schema.
6. Jalankan deterministic verify. Narrative bukan evidence.
7. Repair maksimal lima iterasi; stop pada no-progress fingerprint.
8. Jangan ubah contract, tests, policies, schemas, validator, atau raw evidence.
9. Minta human decision untuk ambiguity, datasheet/package uncertainty, layout
   quality, thermal/SI/RF/mechanical/DFM/compliance, dan fabrication.
10. Report status dan evidence. Selalu nyatakan production/fabrication approval
    belum diberikan.
