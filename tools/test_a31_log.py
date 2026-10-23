import struct
import unittest

from a31_diag_log import inspect

BUILD = 'a' * 40
BEGIN = b'\n[A31-DIAG v1] BEGIN\nBUILD=' + BUILD.encode() + b'\n'
PASS = b'MMU16K PASS\nVTIMER PASS\n[A31-DIAG] PASS\n'
ENTRY_PASS = (b'MMU16K PASS\nVTIMER PASS\nPAYLOAD COPY/READBACK PASS\n'
              b'[A31-DIAG] XNU HANDOFF\n[A31-XNU] ENTRY MMU-OFF v1\n'
              b'[A31-XNU] ENTRY-CHECK PASS\n[A31-XNU] RECOVERY REQUEST\n')


class A31LogTests(unittest.TestCase):
    def test_cpu_data_requires_prior_checkpoints_and_ordered_completion(self):
        rebase = (b'[A31-XNU] C STAGE 1: arm_init entered (MMU on)\n'
                  b'[A31-XNU] ENTRY-CHECK PASS\n'
                  b'[A31-XNU] C STAGE 21: image rebasing done; before boot args and CPU data\n'
                  b'XNU_CURRENT_EL=0x0000000000000001\nXNU_SCTLR_EL1=0x000000003454593d\n'
                  b'XNU_CNTFRQ=0x0000000000c65d40\n[A31-XNU] REBASE-CHECK PASS\n')
        cpu = (b'[A31-XNU] C STAGE 22: boot args copied; CPU data initialized; before platform\n'
               b'[A31-XNU] CPU-DATA-CHECK PASS\n')
        good = ENTRY_PASS.replace(b'[A31-XNU] ENTRY-CHECK PASS\n', rebase + cpu)
        self.assertEqual(inspect(BEGIN + good, BUILD)['status'], 'xnu_cpu_data_pass')
        platform = (b'[A31-XNU] C STAGE 2: PE_init_platform done\n'
                    b'[A31-XNU] PLATFORM-CHECK PASS\n')
        platform_good = good.replace(b'[A31-XNU] RECOVERY REQUEST\n',
                                     platform + b'[A31-XNU] RECOVERY REQUEST\n')
        self.assertEqual(inspect(BEGIN + platform_good, BUILD)['status'], 'xnu_platform_pass')
        bootstrap = (b'[A31-XNU] C STAGE 3: ml_parse_cpu_topology done\n'
                     b'[A31-XNU] TOPOLOGY-CHECK PASS\n'
                     b'[A31-XNU] C STAGE 4: cpu_bootstrap done\n'
                     b'[A31-XNU] CPU-BOOTSTRAP-CHECK PASS\n')
        bootstrap_good = platform_good.replace(b'[A31-XNU] RECOVERY REQUEST\n',
                                               bootstrap + b'[A31-XNU] RECOVERY REQUEST\n')
        self.assertEqual(inspect(BEGIN + bootstrap_good, BUILD)['status'], 'xnu_cpu_bootstrap_pass')
        runtime = (b'[A31-XNU] C STAGE 5: kernel_startup_bootstrap done\n'
                   b'[A31-XNU] STARTUP-LOCKS-CHECK PASS\n'
                   b'[A31-XNU] C STAGE 6: cpu_init done\n'
                   b'[A31-XNU] CPU-INIT-CHECK PASS\n')
        runtime_good = bootstrap_good.replace(b'[A31-XNU] RECOVERY REQUEST\n',
                                              runtime + b'[A31-XNU] RECOVERY REQUEST\n')
        self.assertEqual(inspect(BEGIN + runtime_good, BUILD)['status'], 'xnu_cpu_init_pass')
        for bad in [bootstrap_good, runtime + bootstrap_good,
                    runtime_good.replace(b'[A31-XNU] STARTUP-LOCKS-CHECK PASS\n', b''),
                    runtime_good + b'[A31-XNU] CPU-INIT-CHECK FAIL\n']:
            self.assertFalse(inspect(BEGIN + bad, BUILD)['sessions'][0]['xnu_cpu_init_pass'])
        for bad in [platform_good, bootstrap + platform_good,
                    bootstrap_good.replace(b'[A31-XNU] TOPOLOGY-CHECK PASS\n', b''),
                    bootstrap_good + b'[A31-XNU] CPU-BOOTSTRAP-CHECK FAIL\n']:
            self.assertFalse(inspect(BEGIN + bad, BUILD)['sessions'][0]['xnu_cpu_bootstrap_pass'])
        for bad in [good, platform_good.replace(cpu, b''),
                    platform + good, platform_good + b'[A31-XNU] PLATFORM-CHECK FAIL\n',
                    platform_good + b'[A31-XNU] BOOT EXCEPTION\n']:
            self.assertFalse(inspect(BEGIN + bad, BUILD)['sessions'][0]['xnu_platform_pass'])
        bads = [good.replace(rebase, b''), good.replace(cpu, b''),
                good.replace(rebase + cpu, cpu + rebase),
                good.replace(b'CPU-DATA-CHECK PASS', b'CPU-DATA-CHECK FAIL'),
                good + b'[A31-XNU] PANIC: cpu failure\n',
                good.replace(b'XNU_SCTLR_EL1=0x000000003454593d', b'XNU_SCTLR_EL1=0x000000003454593c')]
        for bad in bads:
            self.assertFalse(inspect(BEGIN + bad, BUILD)['sessions'][0]['xnu_cpu_data_pass'])
        # A later loader session cannot supply the missing completion.
        self.assertFalse(inspect(BEGIN + good.replace(cpu, b'') + BEGIN + cpu, BUILD)['sessions'][0]['xnu_cpu_data_pass'])

    def test_rebase_requires_ordered_native_stages_registers_and_no_failure(self):
        stage = (b'[A31-XNU] C STAGE 21: image rebasing done; before boot args and CPU data\n'
                 b'XNU_CURRENT_EL=0x0000000000000001\nXNU_SCTLR_EL1=0x000000003454593d\n'
                 b'XNU_CNTFRQ=0x0000000000c65d40\n[A31-XNU] REBASE-CHECK PASS\n')
        entry = ENTRY_PASS.replace(b'[A31-XNU] ENTRY-CHECK PASS\n',
                 b'[A31-XNU] C STAGE 1: arm_init entered (MMU on)\n[A31-XNU] ENTRY-CHECK PASS\n')
        good = entry.replace(b'[A31-XNU] RECOVERY REQUEST\n', stage + b'[A31-XNU] RECOVERY REQUEST\n')
        self.assertEqual(inspect(BEGIN + good, BUILD)['status'], 'xnu_rebase_pass')
        bads = [ENTRY_PASS, good.replace(stage, b''),
                good.replace(b'XNU_SCTLR_EL1=0x000000003454593d', b'XNU_SCTLR_EL1=0x000000003454593c'),
                good.replace(b'XNU_CURRENT_EL=0x0000000000000001', b'XNU_CURRENT_EL=0x0000000000000002'),
                good.replace(b'XNU_CNTFRQ=0x0000000000c65d40', b'XNU_CNTFRQ=0x0000000000000001'),
                stage + good.replace(stage, b''), good + b'[A31-XNU] REBASE-CHECK FAIL\n',
                good + b'[A31-XNU] BOOT EXCEPTION\n']
        for bad in bads:
            self.assertFalse(inspect(BEGIN + bad, BUILD)['sessions'][0]['xnu_rebase_pass'])

    def test_early_asm_requires_kernel_marker_and_audited_checkpoint(self):
        records = (b'XNU_ENTRY_PA=0x000000010148c488\nENTRY_TRAP_ELR=0x000000010148e100\n'
                   b'ENTRY_TRAP_TARGET=0x000000010148e100\nENTRY_TRAP_ESR=0x00000000f2000a31\n'
                   b'PAYLOAD COPY/READBACK PASS\nEARLY XNU BRK ARMED\n[A31-DIAG] XNU HANDOFF\n'
                   b'[A31-XNU] ENTRY MMU-OFF v1\nPHYSICAL ENTRY BRK PASS\n')
        result = inspect(BEGIN + records + PASS, BUILD)
        self.assertEqual(result['status'], 'xnu_early_asm_pass')
        self.assertFalse(result['sessions'][0]['xnu_entry_pass'])
        for bad in [records.replace(b'[A31-XNU] ENTRY MMU-OFF v1\n', b''),
                    records.replace(b'ENTRY_TRAP_ELR=0x000000010148e100', b'ENTRY_TRAP_ELR=0x000000010148e104')]:
            self.assertFalse(inspect(BEGIN + bad + PASS, BUILD)['sessions'][0]['xnu_early_asm_pass'])

    def test_entry_trap_is_distinct_from_xnu_execution(self):
        records = (b'XNU_ENTRY_PA=0x000000010148c488\nENTRY_TRAP_ELR=0x000000010148c488\n'
                   b'ENTRY_TRAP_ESR=0x00000000f2000a31\nPAYLOAD COPY/READBACK PASS\n'
                   b'ENTRY BRK ARMED; NO XNU INSTRUCTIONS\n[A31-DIAG] XNU HANDOFF\n'
                   b'PHYSICAL ENTRY BRK PASS\n')
        result = inspect(BEGIN + records + PASS, BUILD)
        self.assertEqual(result['status'], 'entry_trap_pass')
        self.assertFalse(result['sessions'][0]['xnu_entry_pass'])
        for bad in [records.replace(b'f2000a31', b'f2000000'),
                    records.replace(b'ENTRY_TRAP_ELR=0x000000010148c488', b'ENTRY_TRAP_ELR=0x000000010148c48c'),
                    records.replace(b'ENTRY BRK ARMED; NO XNU INSTRUCTIONS\n', b'')]:
            self.assertFalse(inspect(BEGIN + bad + PASS, BUILD)['sessions'][0]['physical_entry_trap_pass'])

    def test_handoff_is_not_kernel_entry_evidence(self):
        self.assertEqual(inspect(BEGIN + ENTRY_PASS.split(b'[A31-XNU]')[0], BUILD)['status'], 'incomplete')

    def test_kernel_entry_requires_all_markers_in_same_session(self):
        self.assertEqual(inspect(BEGIN + ENTRY_PASS, BUILD)['status'], 'xnu_entry_pass')
        for marker in ENTRY_PASS.splitlines(keepends=True):
            self.assertNotEqual(inspect(BEGIN + ENTRY_PASS.replace(marker, b''), BUILD)['status'], 'xnu_entry_pass')

    def test_kernel_failure_overrides_checkpoint_pass(self):
        for error in [b'[A31-XNU] ENTRY-CHECK FAIL\n', b'[A31-XNU] PANIC: failure\n',
                      b'[A31-XNU] RECOVERY FAILED\n', b'[A31-DIAG] FAIL exception\n',
                      b'[A31-XNU] BOOT EXCEPTION\n', b'[A31-XNU] BOOT RECOVERY FAILED\n']:
            self.assertEqual(inspect(BEGIN + ENTRY_PASS + error, BUILD)['status'], 'fail')

    def test_kernel_markers_cannot_be_borrowed_from_next_loader_build(self):
        other = BEGIN.replace(BUILD.encode(), b'b' * 40)
        self.assertEqual(inspect(BEGIN + b'[A31-DIAG] XNU HANDOFF\n' + other + ENTRY_PASS, BUILD)['status'], 'incomplete')
    def test_early_entry_only_does_not_prove_el1_handoff(self):
        result = inspect(BEGIN + b'EARLY_CURRENT_EL=0x0000000000000002\n'
                         b'EARLY ENTRY RECORDED\n', BUILD)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['sessions'][0]['fields']['EARLY_CURRENT_EL'],
                         '0x0000000000000002')

    def test_early_el2_exception_is_a_failed_session(self):
        result = inspect(BEGIN + b'EXCEPTION_EL=0x0000000000000002\n'
                         b'ESR_EL2=0x0000000002000000\n'
                         b'[A31-DIAG] FAIL EL2 entry exception\n', BUILD)
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['sessions'][0]['failure'], 'EL2 entry exception')

    def test_pass_requires_one_matching_build_session(self):
        result = inspect(BEGIN + b'CURRENT_EL=0x0000000000000001\n' + PASS, BUILD)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['sessions'][0]['fields']['CURRENT_EL'], '0x0000000000000001')

    def test_different_build_is_not_evidence(self):
        self.assertEqual(inspect(BEGIN + PASS, 'b' * 40)['status'], 'not_found')

    def test_partial_passes_do_not_prove_completion(self):
        self.assertEqual(inspect(BEGIN + b'MMU16K PASS\n', BUILD)['status'], 'incomplete')

    def test_failure_is_not_overridden_by_pass_text(self):
        self.assertEqual(inspect(BEGIN + b'[A31-DIAG] FAIL exception\n' + PASS, BUILD)['status'], 'fail')

    def test_does_not_borrow_pass_from_next_session(self):
        other = BEGIN.replace(BUILD.encode(), b'b' * 40)
        self.assertEqual(inspect(BEGIN + b'MMU16K PASS\n' + other + PASS, BUILD)['status'], 'incomplete')

    def test_rotated_samsung_ring_is_decoded(self):
        capacity = 0x200000 - 12
        content = BEGIN + PASS
        original = bytes(capacity - len(content)) + content
        position = capacity - 20
        rotated = original[-position:] + original[:-position]
        raw = rotated + struct.pack('<3I', 1, position, 0x4d474f4c)
        self.assertEqual(inspect(raw, BUILD)['status'], 'pass')


if __name__ == '__main__':
    unittest.main()
