IMAGEDIRS := $(shell ls */Dockerfile | xargs dirname)
IMAGES := $(patsubst %,softwareheritage/%,$(IMAGEDIRS))

all: $(IMAGES)
.PHONY: softwareheritage/%

softwareheritage/%: %/Dockerfile
	docker build -t $@:latest -f $< .
