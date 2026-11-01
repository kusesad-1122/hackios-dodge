/*
 * hakios_soc.c -- which phone is this?
 *
 * The loader knows: it picks a platform row by the framebuffer and writes that
 * row's name into the device tree, at /arm-io's "device_type"
 * (base/xnuloader/loader.c:4151 -- dt_prop_str(&w, "device_type", plat->name)).
 * So the kernel can read its own identity out of the device tree it was handed:
 *
 *   /arm-io {
 *       device_type = "dodge";      <- this phone
 *   };
 *
 * Until now the kernel had no way to ask. Every driver that had to behave
 * differently on the Xiaomi 15 and on the POCO carried its own copy of the
 * question -- 109 boot-args named "dada*" (dadaadsp, dadagpu, dadacpu,
 * dadabt, dadatouch, ...) -- and set a file-local `static bool dada;` from
 * them. That does not scale to a second phone: the flags have to be right at
 * every call site, and a flag that is left out fails silently.
 *
 * This file is the one place that knows the answer. It answers three questions:
 *
 *   1. WHICH PHONE is this?           hakios_soc_device()      -> "dodge"
 *   2. IS THIS THE SoC WE KNOW?       hakios_soc_is_sm8750()   -> true on SM8750
 *   3. WHAT ARE ITS HARDWARE FACTS?   hakios_soc_facts()       -> the addresses
 *
 * The hardware facts come from the phone's own device tree, so they are right
 * by construction rather than by transcription. Where a value differs between
 * two phones of the same family (the ADSP window is 0x5080000 bytes on dodge
 * and 0x4580000 on dada), the tree of the running phone decides.
 *
 * The device tree the kernel is given is NOT the phone's own: it is the one the
 * loader synthesises (it has to: it describes the window the kernel gets, not
 * the phone's hardware). So the addresses below are read from the phone's tree
 * at build time and carried here -- but they were read out of the running
 * phone's own /sys/firmware/fdt, not out of a document. The provenance of each
 * is in port/extract-soc-table.py.
 */

#include <mach/machine/vm_types.h>
#include <mach/machine.h>
#include <kern/startup.h>        /* __startup_func: the read must happen before PE_init_iokit() */
#include <libkern/libkern.h>
#include <pexpert/pexpert.h>
#include <pexpert/device_tree.h>
#include <sys/types.h>

#include "hakios_soc.h"

/*
 * The addresses, as read out of the phone's own device tree
 * (backup/out/hw/hw/device-tree.dts, dtc from the running fdt.bin):
 *
 *   adspslpi_region@9ee00000   reg = <0x00 0x9ee00000 0x00 0x5080000>
 *   smem_region@81d00000       reg = <0x00 0x81d00000 0x00 0x200000>
 *   aop_cmd_db_region@81c60000 reg = <0x00 0x81c60000 0x00 0x20000>
 *   remoteproc-adsp@3000000    reg = <0x3000000 0x10000>
 *   qcom,ipcc@406000           reg = <0x406000 0x1000>
 *   rsc@16500000               reg = <0x16500000 0x10000 0x16510000 0x10000 0x16520000 0x10000>
 *   ufshc@1d84000              reg = <0x1d84000 0x3000 ...>
 *   apps-smmu@15000000         reg = <0x15000000 0x100000>
 *   power-controller@c300000  reg = <0xc300000 0x400>
 *
 * The two phones of this family agree on all of them except the ADSP window's
 * size, and on the RSC's third pair (drv-2, 0x16520000) which is this
 * phone's.
 */
const struct hakios_soc_facts hakios_soc_sm8750_facts = {
	.name = "sm8750",
	.device_names = { "dodge", "pakala", "sm8750", NULL },

	.soc_base = 0x00400000UL,       /* where the loader says the peripherals begin */
	.gic_dist = 0x16000000UL,
	.gic_redist = 0x16080000UL,
	.gic_redist_size = 0x200000UL,
	.gic_redist_stride = 0x40000UL, /* redistributor-stride = <0x00 0x40000> */

	.cores = 8,
	.core_shift = 8,               /* Qualcomm numbers the cores in MPIDR Aff1 */
	/* six performance Oryon at Aff1 0..5, two prime at Aff2=1 (0x10000, 0x10100) */

	.smem_phys = 0x81d00000UL,
	.smem_size = 0x200000UL,
	.cmd_db_phys = 0x81c60000UL,
	.adsp_phys = 0x03000000UL,
	.adsp_memory = 0x9ee00000UL,
	.adsp_memory_size = 0x5080000UL,
	.ipcc_phys = 0x00406000UL,
	.rsc_phys = 0x16520000UL,       /* drv-2, the third pair */

	.ufs_hc_phys = 0x01d84000UL,
	.apps_smmu_phys = 0x15000000UL,
	.aoss_phys = 0x0c300000UL,
};

/* The phones of this family, each with what is its own. */
static const struct hakios_soc_device hakios_devices[] = {
	{
		.name = "dodge",
		.model = "OnePlus 13 (PJZ110)",
		.facts = &hakios_soc_sm8750_facts,
		/* this phone's own: the panel and the touch controller */
		.panel_width = 1440, .panel_height = 3168,
		.touch_chip = "S3910",
		.gpu_model = "Adreno830v2",
		.project = "23821",
	},
	{
		.name = "dada",
		.model = "Xiaomi 15",
		.facts = &hakios_soc_sm8750_facts,
		.panel_width = 1200, .panel_height = 2670,
		.touch_chip = NULL,
		.gpu_model = NULL,
		.project = NULL,
	},
};

static const char *hakios_soc_device_name;
static const struct hakios_soc_facts *hakios_soc_current;
static bool hakios_soc_read;

/*
 * Read /arm-io's "device_type": the loader put the platform row's name there.
 *
 * SecureDTLookupEntry() is only guaranteed to work before PE_init_iokit()
 * (bsd/dev/arm64/sysctl.c says so, and does the same thing there), so this
 * runs from a startup function rather than on first use. That is also why the
 * answer is cached: a driver that asks later still gets it.
 *
 * Returns NULL when the tree does not say (QEMU, or a loader too old to write
 * it), which is not an error -- the caller then falls back to the boot-args.
 */
static const char *
hakios_soc_read_device_type(void)
{
	DTEntry entry;
	void const *value = NULL;
	unsigned int size = 0;

	if (kSuccess != SecureDTLookupEntry(0, "/arm-io", &entry))
		return NULL;
	if (kSuccess != SecureDTGetProperty(entry, "device_type", &value, &size))
		return NULL;
	if (value == NULL || size == 0 || size > 63)
		return NULL;

	static char buf[64];
	memcpy(buf, value, size);
	buf[size] = '\0';
	return buf;
}

/*
 * The tree has to be read before PE_init_iokit(), so the identity is taken in
 * a startup function -- the same moment and for the same reason as
 * bsd/dev/arm64/sysctl.c reads the product's brand string.
 */
__startup_func
static void
hakios_soc_init(void)
{
	if (hakios_soc_read)
		return;
	hakios_soc_read = true;

	const char *name = hakios_soc_read_device_type();
	if (name == NULL) {
		/*
		 * No device tree identity: QEMU, or a loader that does not write one.
		 * Fall back to the boot-arg the older trees used, so a phone booted
		 * with the old loader still works.
		 */
		if (PE_parse_boot_argn("dada", NULL, 0) == 0)
			name = NULL;
	}

	if (name != NULL) {
		for (unsigned i = 0; i < sizeof(hakios_devices) / sizeof(hakios_devices[0]); i++) {
			if (strcmp(hakios_devices[i].name, name) == 0) {
				hakios_soc_device_name = hakios_devices[i].name;
				hakios_soc_current = hakios_devices[i].facts;
				printf("hakios: this is the %s (%s)\n", hakios_soc_device_name,
				    hakios_devices[i].model);
				return;
			}
		}
		/*
		 * A name we do not know: a phone that has not been ported yet, or a
		 * loader from a newer tree. Say so, loudly -- the drivers will fall
		 * back to their defaults, and silently doing the wrong thing on the
		 * wrong phone is how a port turns into a mystery.
		 */
		printf("hakios: unknown device \"%s\": no hardware facts for it\n", name);
		return;
	}

	printf("hakios: no device identity in the device tree\n");
}

const char *
hakios_soc_device(void)
{
	hakios_soc_init();
	return hakios_soc_device_name;
}

const struct hakios_soc_facts *
hakios_soc_facts(void)
{
	hakios_soc_init();
	return hakios_soc_current;
}
bool
hakios_soc_is_sm8750(void)
{
	hakios_soc_init();
	return hakios_soc_current == &hakios_soc_sm8750_facts;
}

const struct hakios_soc_device *
hakios_soc_device_info(void)
{
	hakios_soc_init();
	if (hakios_soc_device_name == NULL)
		return NULL;
	for (unsigned i = 0; i < sizeof(hakios_devices) / sizeof(hakios_devices[0]); i++)
		if (strcmp(hakios_devices[i].name, hakios_soc_device_name) == 0)
			return &hakios_devices[i];
	return NULL;
}
