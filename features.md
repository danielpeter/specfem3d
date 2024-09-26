**Table of Contents**

- [Simulation features supported in SPECFEM3D_Cartesian](#simulation-features-supported-in-specfem3d_cartesian)

Simulation features supported in SPECFEM3D_Cartesian
====================================================

The following lists all available features for a SPECFEM3D_Cartesian simulation, where *CPU*, *CUDA* and *HIP* denote the code versions for CPU-only simulations, CUDA and HIP hardware support, respectively.

| **Feature**             |                                      | *CPU* | *CUDA* | *HIP* |
|:------------------------|:-------------------------------------|:-----:|:------:|:-----:|
|                         |                                      |       |        |       |
| **Physics**             | Acoustic                             |   X   |   X    |   X   |
|                         | Elastic                              |   X   |   X    |   X   |
|                         | Poroelastic                          |   X   |   \-   |  \-   |
|                         | Ocean load / Topography              |   X   |   X    |   X   |
|                         | Gravity field / integrals            |   X   |   X    |   X   |
|                         | Anisotropy                           |   X   |   X    |   X   |
|                         | Attenuation                          |   X   |   X    |   X   |
|                         |                                      |       |        |       |
| **Simulation Setup**    | Noise simulations                    |   X   |   X    |   X   |
|                         | Fault rupture dynamic/kinematic      |   X   |   X    |   X   |
|                         | Wavefield injection/coupling         |   X   |   X    |   X   |
|                         | C-PML                                |   X   |   \-   |  \-   |
|                         | Simultaneous runs                    |   X   |   X    |   X   |
|                         | ADIOS file I/O                       |   X   |   X    |   X   |
|                         | HDF5 file I/O                        |   X   |   X    |   X   |
|                         | FWI framework                        |   X   |   X    |   X   |
|                         |                                      |       |        |       |
| **Meshing**             | in-house mesher                      |   X   |   \-   |  \-   |
|                         | external (CUBIT/Trelis,Gmsh)         |   X   |   \-   |  \-   |
|                         | UTM projection                       |   X   |   \-   |  \-   |
|                         | Cavity                               |   X   |   \-   |  \-   |
|                         | SCOTCH/Metis/PaToH/Rows partitioning |   X   |   \-   |  \-   |
|                         |                                      |       |        |       |
| **Sensitivity kernels** | Undoing of attenuation               |   X   |   X    |   X   |
|                         | Anisotropic kernels                  |   X   |   X    |   X   |
|                         | Transversely isotropic kernels       |   X   |   X    |   X   |
|                         | Isotropic kernels                    |   X   |   X    |   X   |
|                         | Moho boundary kernels                |   X   |   \-   |  \-   |
|                         | Approximate Hessian                  |   X   |   X    |   X   |
|                         |                                      |       |        |       |
| **Time schemes**        | Newmark                              |   X   |   X    |   X   |
|                         | LDDRK                                |   X   |   \-   |  \-   |
|                         | local-time stepping (LTS)            |   X   |   \-   |  \-   |
|                         |                                      |       |        |       |
| **Visualization**       | ShakeMap                             |   X   |   X    |   X   |
|                         | Surface movie                        |   X   |   X    |   X   |
|                         | Volumetric movie                     |   X   |   X    |   X   |
|                         | VTK runtime-vis                      |   X   |   X    |   X   |
|                         |                                      |       |        |       |
| **Seismogram formats**  | Ascii                                |   X   |   X    |   X   |
|                         | SU                                   |   X   |   X    |   X   |
|                         | ASDF                                 |   X   |   X    |   X   |
|                         | HDF5                                 |   X   |   X    |   X   |
|                         | Binary                               |   X   |   X    |   X   |
|                         | down-sampling                        |   X   |   X    |   X   |
|                         |                                      |       |        |       |

-----
> This documentation has been automatically generated by [pandoc](http://www.pandoc.org)
> based on the User manual (LaTeX version) in folder doc/USER_MANUAL/
> (Sep 26, 2024)

