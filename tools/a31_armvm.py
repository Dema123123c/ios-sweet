"""Validate quantitative evidence from the A31 arm_vm_init-return checkpoint."""
REQUIRED = ('XNU_PMAP_MEM_BYTES', 'XNU_PMAP_ALLOC_END', 'XNU_ARMVM_ALLOC_BEGIN',
            'XNU_ARMVM_ALLOC_END', 'XNU_ARMVM_ALLOC_LIMIT', 'XNU_ARMVM_PT_PAGES',
            'XNU_ARMVM_LEAF_PAGES', 'XNU_ARMVM_PREEMPT_BEFORE', 'XNU_ARMVM_PREEMPT_AFTER',
            'XNU_ARMVM_PENDING_AST', 'XNU_ARMVM_FIRST_AVAIL', 'XNU_ARMVM_IO_START',
            'XNU_ARMVM_IO_END', 'XNU_ARMVM_COPY_START', 'XNU_ARMVM_COPY_END')


def check_armvm_fields(fields):
    try:
        if any(name not in fields for name in REQUIRED):
            return False
        v = {name: int(fields[name], 16) for name in REQUIRED}
        if any(n < 0 or n >= 1 << 64 for n in v.values()):
            return False
    except (TypeError, ValueError):
        return False
    begin, end, limit = (v['XNU_ARMVM_ALLOC_' + name] for name in ('BEGIN', 'END', 'LIMIT'))
    pages, leaves = v['XNU_ARMVM_PT_PAGES'], v['XNU_ARMVM_LEAF_PAGES']
    io_start, io_end = v['XNU_ARMVM_IO_START'], v['XNU_ARMVM_IO_END']
    return (0x4000000 <= v['XNU_PMAP_MEM_BYTES'] <= 0x3fd00000 and
            0x100000000 <= begin == v['XNU_PMAP_ALLOC_END'] < end <= limit <= 0x13fd00000 and
            limit <= 0x100000000 + v['XNU_PMAP_MEM_BYTES'] and not (begin | end | limit) & 0x3fff and
            0 < leaves <= pages <= 32 and end - begin == pages * 0x4000 and
            v['XNU_ARMVM_FIRST_AVAIL'] == end and
            v['XNU_ARMVM_PREEMPT_BEFORE'] == v['XNU_ARMVM_PREEMPT_AFTER'] <= 1024 and
            v['XNU_ARMVM_PENDING_AST'] == 0 and
            0xfffffe0006000000 <= io_start < io_end < 0xfffffe8fffdfc000 and
            io_end - io_start <= 0x8000000 and not io_start & 0x1ffffff and not io_end & 0x7fffff and
            v['XNU_ARMVM_COPY_START'] == 0xfffffe8fffdfc000 and
            v['XNU_ARMVM_COPY_END'] == 0xfffffe8fffffffff)
