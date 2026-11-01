/*
 * hakios_soc.h -- which phone is this?
 *
 * One place that answers it, so that no driver has to carry its own copy of
 * the question. See hakios_soc.c for where the numbers come from.
 */

#ifndef _HAKIOS_SOC_H
#define _HAKIOS_SOC_H

#include <stdbool.h>
#include <sys/types.h>

/*
 * The hardware facts of a phone: what its SoC is, and where its blocks live.
 * Every value was read out of the phone's own device tree.
 */
struct hakios_soc_facts {
	const char *name;                    /* the SoC's family: "sm8750" */
	const char *const *device_names;     /* the phones of this family */

	uint64_t soc_base;                   /* where the loader says the peripherals begin */
	uint64_t gic_dist, gic_redist;
	uint64_t gic_redist_size;
	uint64_t gic_redist_stride;

	int cores;
	int core_shift;                      /* the bit of MPIDR the cores are numbered in */

	uint64_t smem_phys, smem_size;
	uint64_t cmd_db_phys;
	uint64_t adsp_phys;                  /* the ADSP remoteproc */
	uint64_t adsp_memory, adsp_memory_size;
	uint64_t ipcc_phys;
	uint64_t rsc_phys;                   /* drv-2, the third pair */

	uint64_t ufs_hc_phys;
	uint64_t apps_smmu_phys;
	uint64_t aoss_phys;
};

/* What is this phone's own, as opposed to its SoC's. */
struct hakios_soc_device {
	const char *name;                    /* "dodge", "dada" */
	const char *model;                   /* "OnePlus 13 (PJZ110)" */
	const struct hakios_soc_facts *facts;

	uint32_t panel_width, panel_height;
	const char *touch_chip;
	const char *gpu_model;
	const char *project;                 /* the vendor's project number */
};

/*
 * The phone's name ("dodge"), or NULL when the tree does not say.
 * The tree is read once, in a startup function; this just hands back the answer.
 */
const char *hakios_soc_device(void);

/* The hardware facts of the SoC, or NULL when the phone is unknown. */
const struct hakios_soc_facts *hakios_soc_facts(void);

/* True when this is one of the phones of the SM8750 family. */
bool hakios_soc_is_sm8750(void);

/* The phone's own facts (panel, touch, GPU), or NULL. */
const struct hakios_soc_device *hakios_soc_device_info(void);

#endif /* _HAKIOS_SOC_H */
