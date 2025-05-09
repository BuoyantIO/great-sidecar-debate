import sys

import csv
import datetime

import matplotlib.pyplot as plt
# import matplotlib.colors as pltcolors
import numpy as np
# from numpy.polynomial import Polynomial

reader = csv.DictReader(open("OUT/gke-20250425T1222-3workers/linkerd-00/600-1-metrics.csv", "r"))

timestamps = []
mc = []

for row in reader:
    timestamps.append(datetime.datetime.strptime(row['timestamp'], "%Y-%m-%d %H:%M:%S"))
    mc.append(int(row['data-plane CPU']) / 1_000_000)

deltas = [(x - timestamps[0]).seconds for x in timestamps]

# Plot the raw data
fig = plt.figure(figsize=(10, 6))
ax = fig.add_axes([0.1, 0.1, 0.8, 0.8])
ax.set_title("Raw data-plane CPU through a five-minute run")
ax.set_xlabel("Time (s)")
ax.set_ylabel("CPU (mC)")

ax.plot(np.array(deltas), np.array(mc), marker="o", label="CPU (mC)")
ax.legend(loc="best")
ylim = ax.get_ylim()

fig.savefig("raw-data-plane-0.png")

mean = np.array(mc).mean()

ax.plot([0, max(deltas)], [mean, mean], label="Mean", linestyle="--")
ax.legend(loc="best")

fig.savefig("raw-data-plane-1.png")

filtered_mc_1 = []
filtered_deltas_1 = []

for i in range(len(mc)):
    if mc[i] >= mean:
        filtered_mc_1.append(mc[i])
        filtered_deltas_1.append(deltas[i])

# Next, calculate mean and standard deviation for this filtered data set...
mean = np.mean(filtered_mc_1)
stddev = 1 * np.std(filtered_mc_1)

# Plot the filtered data with mean and stddev lines
fig = plt.figure(figsize=(10, 6))
ax = fig.add_axes([0.1, 0.1, 0.8, 0.8])
ax.set_title("Filtered data-plane CPU (pass 1)")
ax.set_xlabel("Time (s)")
ax.set_ylabel("CPU (mC)")
ax.set_ylim(ylim)

ax.plot(np.array(filtered_deltas_1), np.array(filtered_mc_1), marker="o", label="CPU (mC)")
ax.legend(loc="best")

fig.savefig("filtered-data-plane-0.png")

ax.plot([0, max(filtered_deltas_1)], [mean, mean], label="Mean", linestyle="--")
ax.plot([0, max(filtered_deltas_1)], [mean + stddev, mean + stddev], label="Mean + 1 StdDev", linestyle="--")
ax.plot([0, max(filtered_deltas_1)], [mean - stddev, mean - stddev], label="Mean - 1 StdDev", linestyle="--")
ax.legend(loc="best")

fig.savefig("filtered-data-plane-1.png")

# ...and filter out outliers again.

filtered_mc_2 = []
filtered_deltas_2 = []

for i in range(len(filtered_mc_1)):
    if np.abs(filtered_mc_1[i] - mean) <= stddev:
        filtered_mc_2.append(filtered_mc_1[i])
        filtered_deltas_2.append(filtered_deltas_1[i])

# Plot the filtered data
fig = plt.figure(figsize=(10, 6))
ax = fig.add_axes([0.1, 0.1, 0.8, 0.8])
ax.set_title("Filtered data-plane CPU (pass 2)")
ax.set_xlabel("Time (s)")
ax.set_ylabel("CPU (mC)")
ax.set_ylim(ylim)

ax.plot(np.array(filtered_deltas_2), np.array(filtered_mc_2), marker="o", label="CPU (mC)")
ax.legend(loc="best")

fig.savefig("filtered-data-plane-2.png")

plt.show()

