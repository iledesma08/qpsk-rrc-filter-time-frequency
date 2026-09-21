# Serial RTL with vector matching before optimizing

Every PPA optimization starts from a working serial RTL with 100% vector matching against `sim/vectors/`.

We avoid optimizing a design with no reference: the serial version sets the correctness and PPA baseline against which unfolded/pipeline/systolic/folded are measured.
