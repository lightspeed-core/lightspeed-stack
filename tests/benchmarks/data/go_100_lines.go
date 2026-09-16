// 100 lines of go
package main

import (
	"errors"
	"fmt"
	"log"
	"os"
)

// FractalParameter structure contains information about all fractal parameters.
type FractalParameter struct {
	Name      string  `toml:"name"`
	Type      string  `toml:"type"`
	Class     string  `toml:"class"`
	Cx0       float64 `toml:"cx0"`
	Cy0       float64 `toml:"cy0"`
	Palette   Palette `toml:"palette"`
	Maxiter   uint    `toml:"maxiter"`
	Bailout   uint    `toml:"bailout"`
	Function1 string  `toml:"function1"`
	Function2 string  `toml:"function2"`
	Xmin      float64 `toml:"xmin"`
	Ymin      float64 `toml:"ymin"`
	Xmax      float64 `toml:"xmax"`
	Ymax      float64 `toml:"ymax"`
	A         float64 `toml:"A"`
	Scale     float64 `toml:"scale"`
	XOffset   float64 `toml:"x_offset"`
	YOffset   float64 `toml:"y_offset"`
}

// Sequence of fractal parameters
type FractalParameters struct {
	Parameters []FractalParameter `toml:"fractal"`
}

// LoadFractalParameters function reads fractal parameters from external text file
func LoadFractalParameters(filename string) (map[string]FractalParameter, error) {
	var parameters FractalParameters
	asMap := map[string]FractalParameter{}

	_, err := os.Stat(filename)

	if os.IsNotExist(err) {
		return asMap, errors.New("Parameter file does not exist.")
	}
	if err != nil {
		log.Fatal(err)
		return asMap, err
	}

	for _, parameter := range parameters.Parameters {
		if _, exists := asMap[parameter.Name]; exists {
			return asMap, fmt.Errorf(
				"duplicate parameter name %q in %s",
				parameter.Name, filename)
		}
		if parameter.Palette.Name == "" {
			parameter.Palette.Slope = 1
		}
		asMap[parameter.Name] = parameter
	}
	return asMap, nil
}

// Resolution describes the image dimensions in pixels.
type Resolution struct {
	Width  uint
	Height uint
}

// NewResolution constructs a Resolution with the given width and height.
// Width and height are expected to be positive numbers.
func NewResolution(width, height uint) (Resolution, error) {
	// Check for zero dimensions
	if width == 0 {
		return Resolution{}, errors.New("width cannot be zero")
	}
	if height == 0 {
		return Resolution{}, errors.New("height cannot be zero")
	}

	const maxDimension = 65535 // 2^16 - 1, reasonable for image processing
	if width > maxDimension {
		return Resolution{}, fmt.Errorf("width %d exceeds maximum allowed dimension %d", width, maxDimension)
	}
	if height > maxDimension {
		return Resolution{}, fmt.Errorf("height %d exceeds maximum allowed dimension %d", height, maxDimension)
	}

	return Resolution{
		Width:  width,
		Height: height,
	}, nil
}

func main() {
	fmt.Println("100 lines")
}
