!=====================================================================
!
!                          S p e c f e m 3 D
!                          -----------------
!
!     Main historical authors: Dimitri Komatitsch and Jeroen Tromp
!                              CNRS, France
!                       and Princeton University, USA
!                 (there are currently many more authors!)
!                           (c) October 2017
!
! This program is free software; you can redistribute it and/or modify
! it under the terms of the GNU General Public License as published by
! the Free Software Foundation; either version 3 of the License, or
! (at your option) any later version.
!
! This program is distributed in the hope that it will be useful,
! but WITHOUT ANY WARRANTY; without even the implied warranty of
! MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
! GNU General Public License for more details.
!
! You should have received a copy of the GNU General Public License along
! with this program; if not, write to the Free Software Foundation, Inc.,
! 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
!
!=====================================================================


  subroutine prepare_oceans()

! prepares arrays for coupling with oceans
!
! note: handling of coupling on GPU needs to avoid using a mutex to update acceleration;
!       tests so far have shown, that with a simple mutex implementation
!       the results differ between successive runs (probably still due to some race conditions?)
!
!       here we now totally avoid mutex usage and still update each global point only once,
!       also facilitating vectorization of the updating loop

  use specfem_par
  use specfem_par_elastic

  implicit none
  ! local parameters
  integer :: ipoin,ispec,iface,igll,i,j,k,iglob,ier
  integer :: npoin_oceans_all
  ! flag to mask ocean-bottom degrees of freedom for ocean load
  logical, dimension(:), allocatable :: updated_dof_ocean_load
  real(kind=CUSTOM_REAL), dimension(:), allocatable :: normx, normy, normz
  real(kind=CUSTOM_REAL) :: norm,nx,ny,nz

  ! checks if anything to do
  if (.not. APPROXIMATE_OCEAN_LOAD) return
  if (.not. ELASTIC_SIMULATION) return

  ! user info
  if (myrank == 0) then
    write(IMAIN,*) "preparing oceans arrays"
    call flush_IMAIN()
  endif

  ! mask
  allocate(updated_dof_ocean_load(NGLOB_AB),stat=ier)
  if (ier /= 0) stop 'Error allocating arrays updated_dof_ocean_load'
  updated_dof_ocean_load(:) = .false.

  ! For norms
  allocate(normx(NGLOB_AB),stat=ier)
  if (ier /= 0) stop 'Error allocating arrays normx (ocean load)'
  normx(:) = 0.0_CUSTOM_REAL
  allocate(normy(NGLOB_AB),stat=ier)
  if (ier /= 0) stop 'Error allocating arrays normy (ocean load)'
  normy(:) = 0.0_CUSTOM_REAL
  allocate(normz(NGLOB_AB),stat=ier)
  if (ier /= 0) stop 'Error allocating arrays normz (ocean load)'
  normz(:) = 0.0_CUSTOM_REAL

  ! counts global points on surface to oceans
  ipoin = 0
  do iface = 1,num_free_surface_faces
    ispec = free_surface_ispec(iface)

    ! only relevant for elastic elements
    if (ispec_is_elastic(ispec)) then
      ! loop over surface points
      do igll = 1, NGLLSQUARE
        i = free_surface_ijk(1,igll,iface)
        j = free_surface_ijk(2,igll,iface)
        k = free_surface_ijk(3,igll,iface)

        ! get global point number
        iglob = ibool(i,j,k,ispec)

        ! only update once
        if (.not. updated_dof_ocean_load(iglob)) then
          ipoin = ipoin + 1
          updated_dof_ocean_load(iglob) = .true.
        endif
      enddo   ! igll
    endif
  enddo   ! iface
  npoin_oceans = ipoin

  ! total for all processes
  call sum_all_i(npoin_oceans,npoin_oceans_all)

  ! user info
  if (myrank == 0) then
    write(IMAIN,*) "  number of global points on oceans (in slice 0) = ",npoin_oceans
    write(IMAIN,*) "  total number of global points on oceans        = ",npoin_oceans_all
    call flush_IMAIN()
  endif

  ! determines normals on global points
  do iface = 1,num_free_surface_faces
    ispec = free_surface_ispec(iface)

    ! only relevant for elastic elements
    if (ispec_is_elastic(ispec)) then
      ! loop over surface points
      do igll = 1, NGLLSQUARE
        i = free_surface_ijk(1,igll,iface)
        j = free_surface_ijk(2,igll,iface)
        k = free_surface_ijk(3,igll,iface)

        ! get global point number
        iglob = ibool(i,j,k,ispec)

        ! resulting normal (e.g., on shared points)
        normx(iglob) = normx(iglob) + free_surface_normal(1,igll,iface)
        normy(iglob) = normy(iglob) + free_surface_normal(2,igll,iface)
        normz(iglob) = normz(iglob) + free_surface_normal(3,igll,iface)
      enddo
    endif
  enddo

  ! Assemble normals
  ! note: having multiple MPI slices, the normal on a halo point that is shared between MPI slices might be slightly different
  !       depending from which slice it is taken. to avoid such a jump, here we average the normal
  !       across different MPI slices.
  ! assembles normal values from halo points
  call assemble_MPI_scalar_blocking(NPROC,NGLOB_AB, &
                                    normx, &
                                    num_interfaces_ext_mesh,max_nibool_interfaces_ext_mesh, &
                                    nibool_interfaces_ext_mesh,ibool_interfaces_ext_mesh, &
                                    my_neighbors_ext_mesh)

  call assemble_MPI_scalar_blocking(NPROC,NGLOB_AB, &
                                    normy, &
                                    num_interfaces_ext_mesh,max_nibool_interfaces_ext_mesh, &
                                    nibool_interfaces_ext_mesh,ibool_interfaces_ext_mesh, &
                                    my_neighbors_ext_mesh)

  call assemble_MPI_scalar_blocking(NPROC,NGLOB_AB, &
                                    normz, &
                                    num_interfaces_ext_mesh,max_nibool_interfaces_ext_mesh, &
                                    nibool_interfaces_ext_mesh,ibool_interfaces_ext_mesh, &
                                    my_neighbors_ext_mesh)

  ! normalize resulting normals
  do iglob = 1,NGLOB_AB
    ! resulting normal (e.g., on shared points)
    nx = normx(iglob)
    ny = normy(iglob)
    nz = normz(iglob)

    ! gets vector norm
    norm = sqrt( nx*nx + ny*ny + nz*nz)

    ! normalize
    if (abs(norm) < TINYVAL_SNGL) then
      ! normal cancelled out (or wasn't set on global point)
      normx(iglob) = 0.0_CUSTOM_REAL
      normy(iglob) = 0.0_CUSTOM_REAL
      normz(iglob) = 0.0_CUSTOM_REAL
      !debug
      !if (updated_dof_ocean_load(iglob)) then
      !  ! node is a surface ocean load node and should have non-zero norm,
      !  ! unless sum of all shared point normals cancel out
      !  print *,'Warning: ocean load node ',iglob,' has resulting normal with zero length',nx,ny,nz
      !endif
    else
      normx(iglob) = nx / norm
      normy(iglob) = ny / norm
      normz(iglob) = nz / norm
    endif
  enddo

  ! allocates arrays with all global points on ocean surface
  allocate(ibool_ocean_load(npoin_oceans), &
           normal_ocean_load(NDIM,npoin_oceans), &
           rmass_ocean_load_selected(npoin_oceans),stat=ier)
  if (ier /= 0 ) stop 'Error allocating oceans arrays'
  ibool_ocean_load(:) = 0
  normal_ocean_load(:,:) = 0._CUSTOM_REAL
  rmass_ocean_load_selected(:) = 0._CUSTOM_REAL

  ! fills arrays for coupling surface at oceans
  updated_dof_ocean_load(:) = .false.
  ipoin = 0
  do iface = 1,num_free_surface_faces
    ispec = free_surface_ispec(iface)

    ! only relevant for elastic elements
    if (ispec_is_elastic(ispec)) then
      ! loop over surface points
      do igll = 1, NGLLSQUARE
        i = free_surface_ijk(1,igll,iface)
        j = free_surface_ijk(2,igll,iface)
        k = free_surface_ijk(3,igll,iface)

        ! get global point number
        iglob = ibool(i,j,k,ispec)

        ! updates once
        if (.not. updated_dof_ocean_load(iglob)) then
          ipoin = ipoin + 1

          ! fills arrays
          ibool_ocean_load(ipoin) = iglob
          rmass_ocean_load_selected(ipoin) = rmass_ocean_load(iglob)

          ! normal
          normal_ocean_load(1,ipoin) = normx(iglob)
          normal_ocean_load(2,ipoin) = normy(iglob)
          normal_ocean_load(3,ipoin) = normz(iglob)

          ! masks this global point
          updated_dof_ocean_load(iglob) = .true.
        endif
      enddo
    endif
  enddo

  ! frees memory
  deallocate(updated_dof_ocean_load)
  deallocate(normx,normy,normz)

  ! array `rmass_ocean_load` which was read in from mesher is not used anymore, replaced by `rmass_ocean_load_selected` array
  deallocate(rmass_ocean_load)

  ! synchronizes processes
  call synchronize_all()

  end subroutine prepare_oceans
