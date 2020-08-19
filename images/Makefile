IMAGEDIRS := $(shell ls */Dockerfile | xargs dirname)
IMAGES := $(patsubst %,softwareheritage/%,$(IMAGEDIRS))

all: $(IMAGES)
.PHONY: softwareheritage/%

softwareheritage/%: %/Dockerfile
	./build_images.sh
