.. highlight:: bash

.. _installation:

How to Set Up a Software Heritage Archive
=========================================

This series of guides will help you install a (partial) Software Heritage
Instance in a production system.


The global :ref:`architecture of the Software Heritage Archive <architecture>`
looks like:

.. thumbnail:: images/general-architecture.svg

   General view of the |swh| architecture.

Each component can be installed alone, however there are some dependencies
between those services.

The base system used for these guides is a Debian system running the latest
stable version.

Components of the archicture can be installed on a sigle node (not recommended)
or on set (cluster) of machines.


.. _swh_debian_repo:

Debian Repository
~~~~~~~~~~~~~~~~~

On each machine, the Software Heritage apt repository must be configured::

  ~$ sudo apt install apt-transport-https lsb-release
  ~$ echo deb [trusted=yes] https://debian.softwareheritage.org/ $(lsb_release -cs)-swh main | \
        sudo sh -c 'cat > /etc/apt/sources.list.d/softwareheritage.list'
  ~$ sudo apt update



.. toctree::

   install-objstorage
