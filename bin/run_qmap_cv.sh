#!/bin/bash
#SBATCH --nodes=1
#SBATCH --time=0-2:00:00
#SBATCH --mem=5gb
#SBATCH --ntasks-per-node=1
#SBATCH --job-name=qmap-cv
#SBATCH --partition short
#SBATCH --output=logs/slurm-%A.out

source ~/.bashrc
echo Running on host `hostname`
echo Time is `date`
echo Directory is `pwd`
echo Slurm job ID is $SLURM_JOBID
echo This jobs runs on the following machines:
echo $SLURM_JOB_NODELIST

# print out stuff to tell you when the script is running
echo running quantile mapping cross-validation
dt=$(date '+%d/%m/%Y %H:%M:%S');
echo "$dt"

# either run the script to train your model
srun python -m scripts.qmap_cv

dt=$(date '+%d/%m/%Y %H:%M:%S');
echo "$dt"
 