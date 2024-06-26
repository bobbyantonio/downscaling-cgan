#!/bin/bash
#SBATCH --nodes=1
#SBATCH --time=0-20:00:00
#SBATCH --mem=50gb
#SBATCH --ntasks-per-node=1
#SBATCH --job-name=tfrecords-creation
#SBATCH --partition short
#SBATCH --array=0-23
#SBATCH --output=logs/tfrecords-%A_%a.out

echo `which python`
echo Running on host `hostname`
echo Time is `date`
echo Directory is `pwd`
echo Slurm job ID is $SLURM_JOBID
echo This jobs runs on the following machines:
echo $SLURM_JOB_NODELIST

# print out stuff to tell you when the script is running
echo running model
dt=$(date '+%d/%m/%Y %H:%M:%S');
echo "$dt"

# either run the script to train your model
srun python -m dsrnngan.data.tfrecords_generator --records-folder /user/work/uz22147/tfrecords/ --fcst-hours ${SLURM_ARRAY_TASK_ID} --data-config-path /user/home/uz22147/repos/downscaling-cgan/config/data_config_nologs_separate_lakes.yaml --model-config-path /user/home/uz22147/repos/downscaling-cgan/config/model_config_medium-cl50-nologs-nocrop.yaml

dt=$(date '+%d/%m/%Y %H:%M:%S');
echo "$dt"
 
