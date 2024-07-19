#!/bin/bash
#SBATCH --nodes=1
#SBATCH --time=3-0:00:00
#SBATCH --mem=300gb
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --job-name=bootstrap
#SBATCH --partition short,dmm,compute
#SBATCH --output=logs/bstrap-fss-%A.out

# source ~/.bashrc
# source ~/.initConda.sh

echo Running on host `hostname`
echo Time is `date`
echo Directory is `pwd`
echo Slurm job ID is $SLURM_JOBID
echo This jobs runs on the following machines:
echo $SLURM_JOB_NODELIST

# print out stuff to tell you when the script is running
echo running bootstrapping fss
dt=$(date '+%d/%m/%Y %H:%M:%S');
echo "$dt"

# srun python -m scripts.bootstrap_fss --log-folder /user/work/uz22147/logs/cgan/7c4126e641f81ae0_medium-cl100-final-nologs/n4000_202010-202109_45682_e20 --model-number 217600 --n-bootstrap-samples 50 

srun python -m scripts.bootstrap_fss --log-folder /user/work/uz22147/logs/cgan/7c4126e641f81ae0_medium-cl100-final-nologs/n2088_201803-201805_f37bd_e1 --model-number 217600 --n-bootstrap-samples 50 --area kenya

dt=$(date '+%d/%m/%Y %H:%M:%S');
echo "$dt"
