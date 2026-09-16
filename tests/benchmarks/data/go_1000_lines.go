// 1000 lines of Go

package main

import (
	"errors"
	"fmt"
	"image"
	"log"
	"math"
	"math/cmplx"
	"os"
)

// IImage is representation of raster image consisting of IPixels
type IImage [][]IPixel

// NewIImage constructs new instance of ZImage
func NewIImage(resolution Resolution) IImage {
	iimage := make([][]IPixel, resolution.Height)
	for y := uint(0); y < resolution.Height; y++ {
		iimage[y] = make([]IPixel, resolution.Width)
	}
	return iimage
}

// IPixel is a representation of pixel as one unsigned integer value
type IPixel uint64

// RImage is representation of raster image consisting of RPixels
type RImage [][]RPixel

// NewRImage constructs new instance of RImage
func NewRImage(resolution Resolution) RImage {
	rimage := make([][]RPixel, resolution.Height)
	for y := uint(0); y < resolution.Height; y++ {
		rimage[y] = make([]RPixel, resolution.Width)
	}
	return rimage
}

// calcuate minimum and maximum pixel value
func (image *RImage) minMax(width, height uint) (float64, float64) {
	min := float64(math.Inf(1))
	max := float64(math.Inf(-1))

	for j := range height {
		for i := range width {
			z := float64((*image)[j][i])
			if max < z {
				max = z
			}
			if min > z {
				min = z
			}
		}
	}
	return min, max
}

// RPixel is a representation of pixel as one real value
type RPixel float64

// ZImage is representation of raster image consisting of ZPixels
type ZImage [][]ZPixel

// NewZImage constructs new instance of ZImage
func NewZImage(resolution Resolution) ZImage {
	zimage := make([][]ZPixel, resolution.Height)
	for y := uint(0); y < resolution.Height; y++ {
		zimage[y] = make([]ZPixel, resolution.Width)
	}
	return zimage
}

// ZPixel is a representation of pixel in complex plane
type ZPixel complex128

// Palette structure
type Palette struct {
	Name  string `toml:"name"`
	Shift int    `toml:"shift"`
	Slope int    `toml:"slope"`
}

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
	B         float64 `toml:"B"`
	C         float64 `toml:"C"`
	D         float64 `toml:"D"`
	Scale     float64 `toml:"scale"`
	XOffset   float64 `toml:"x_offset"`
	YOffset   float64 `toml:"y_offset"`
}

// FractalParameter2 structure contains information about all fractal parameters.
type FractalParameter2 struct {
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
	B         float64 `toml:"B"`
	C         float64 `toml:"C"`
	D         float64 `toml:"D"`
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
	// check for zero dimensions
	if width == 0 {
		return Resolution{}, errors.New("width cannot be zero")
	}

	// check for zero dimensions
	if height == 0 {
		return Resolution{}, errors.New("height cannot be zero")
	}

	// Check for reasonable maximum dimensions to prevent memory issues
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

func getSteps(
	params FractalParameter,
	image Image) (float64, float64) {
	stepX := float64(params.Xmax-params.Xmin) / float64(image.Resolution.Width)
	stepY := float64(params.Ymax-params.Ymin) / float64(image.Resolution.Height)
	return stepX, stepY
}

func calcIndex(params FractalParameter, i uint) uint {
	index := params.Palette.Shift + int(i)*params.Palette.Slope
	if index < 0 {
		return 0
	}
	return uint(index)
}

// Image structure
type Image struct {
	Resolution Resolution
	Z          ZImage
	R          RImage
	I          IImage
	RGBA       *image.NRGBA
}

// Image constructor
func New(width uint, height uint) (Image, error) {
	resolution, err := NewResolution(width, height)

	if err != nil {
		return Image{}, err
	}

	return Image{
		Resolution: resolution,
		Z:          NewZImage(resolution),
		R:          NewRImage(resolution),
		I:          NewIImage(resolution),
	}, nil
}

// Palette represents color palette used to map fractal calculation result
// (number of iterations, for example) into RGB or RGBA color. Palettes have
// usually 256 records, but it can be more or less.
type RGBPalette [][]byte

func (i *Image) ApplyPalette(palette RGBPalette) {
	r := i.Resolution
	i.RGBA = image.NewNRGBA(image.Rect(0, 0, int(r.Width), int(r.Height)))

	for y := 0; y < int(r.Height); y++ {
		offset := i.RGBA.PixOffset(0, y)
		for x := uint(0); x < r.Width; x++ {
			index := byte(i.I[y][x])
			i.RGBA.Pix[offset] = palette[index][0]
			offset++
			i.RGBA.Pix[offset] = palette[index][1]
			offset++
			i.RGBA.Pix[offset] = palette[index][2]
			offset++
			i.RGBA.Pix[offset] = 0xff
			offset++
		}
	}
}

func (image *Image) RImage2IImage() {
	r := image.Resolution
	width := r.Width
	height := r.Height

	min, max := image.R.minMax(width, height)
	k := 255.0 / (max - min)

	for y := uint(0); y < height; y++ {
		for x := uint(0); x < width; x++ {
			f := float64(image.R[y][x])
			f -= min
			f *= k
			if f > 255.0 {
				f = 255
			}
			i := int(f) & 255
			image.Z[y][x] = ZPixel(complex(float32(x), float32(y)))
			image.I[y][x] = IPixel(i)
		}
	}
}

func (image *Image) RImage2IImageWithFactor(maxFactor float64) {
	r := image.Resolution
	width := r.Width
	height := r.Height

	min, max := image.R.minMax(width, height)
	max *= maxFactor
	k := 255.0 / (max - min)

	for y := uint(0); y < height; y++ {
		for x := uint(0); x < width; x++ {
			f := float64(image.R[y][x])
			f -= min
			f *= k
			if f > 255.0 {
				f = 255
			}
			i := int(f) & 255
			image.Z[y][x] = ZPixel(complex(float32(x), float32(y)))
			image.I[y][x] = IPixel(i)
		}
	}
}

// CalcBarnsleyJuliaJ1 calculates Barnsley J1 Mandelbrot-like set
func CalcBarnsleyJuliaJ1(
	params FractalParameter,
	image Image) {

	stepX, stepY := getSteps(params, image)

	cx := params.Cx0
	cy := params.Cy0
	var zy0 float64 = params.Ymin
	for y := uint(0); y < image.Resolution.Height; y++ {
		var zx0 float64 = params.Xmin
		for x := uint(0); x < image.Resolution.Width; x++ {
			var zx float64 = zx0
			var zy float64 = zy0
			var i uint
			for i < params.Maxiter {
				var zxn float64
				var zyn float64
				zx2 := zx * zx
				zy2 := zy * zy
				if zx2+zy2 > float64(params.Bailout) {
					break
				}
				if zx >= 0 {
					zxn = zx*cx - zy*cy - cx
					zyn = zx*cy + zy*cx - cy
				} else {
					zxn = zx*cx - zy*cy + cx
					zyn = zx*cy + zy*cx + cy
				}
				zx = zxn
				zy = zyn
				i++
			}
			image.Z[y][x] = ZPixel(complex(zx, zy))
			image.I[y][x] = IPixel(calcIndex(params, i))
			zx0 += stepX
		}
		zy0 += stepY
	}
}

// CalcBarnsleyJuliaJ2 calculates Barnsley J2 Mandelbrot-like set
func CalcBarnsleyJuliaJ2(
	params FractalParameter,
	image Image) {

	stepX, stepY := getSteps(params, image)

	cx := params.Cx0
	cy := params.Cy0
	var zy0 float64 = params.Ymin
	for y := uint(0); y < image.Resolution.Height; y++ {
		var zx0 float64 = params.Xmin
		for x := uint(0); x < image.Resolution.Width; x++ {
			var zx float64 = zx0
			var zy float64 = zy0
			var i uint
			for i < params.Maxiter {
				var zxn float64
				var zyn float64
				zx2 := zx * zx
				zy2 := zy * zy
				if zx2+zy2 > float64(params.Bailout) {
					break
				}
				if zx*cy+zy*cx >= 0 {
					zxn = zx*cx - zy*cy - cx
					zyn = zx*cy + zy*cx - cy
				} else {
					zxn = zx*cx - zy*cy + cx
					zyn = zx*cy + zy*cx + cy
				}
				zx = zxn
				zy = zyn
				i++
			}
			image.Z[y][x] = ZPixel(complex(zx, zy))
			image.I[y][x] = IPixel(calcIndex(params, i))
			zx0 += stepX
		}
		zy0 += stepY
	}
}

// CalcBarnsleyMandelbrotM1 calculates Barnsley M1 Mandelbrot-like set
func CalcBarnsleyMandelbrotM1(
	params FractalParameter,
	image Image) {

	stepX, stepY := getSteps(params, image)

	var cy float64 = params.Ymin
	for y := uint(0); y < image.Resolution.Height; y++ {
		var cx float64 = params.Xmin
		for x := uint(0); x < image.Resolution.Width; x++ {
			var zx float64 = cx
			var zy float64 = cy
			var i uint
			for i < params.Maxiter {
				var zxn float64
				var zyn float64
				zx2 := zx * zx
				zy2 := zy * zy
				if zx2+zy2 > float64(params.Bailout) {
					break
				}
				if zx >= 0 {
					zxn = zx*cx - zy*cy - cx
					zyn = zx*cy + zy*cx - cy
				} else {
					zxn = zx*cx - zy*cy + cx
					zyn = zx*cy + zy*cx + cy
				}
				zx = zxn
				zy = zyn
				i++
			}
			image.Z[y][x] = ZPixel(complex(zx, zy))
			image.I[y][x] = IPixel(calcIndex(params, i))
			cx += stepX
		}
		cy += stepY
	}
}

// CalcBarnsleyMandelbrotM2 calculates Barnsley M2 Mandelbrot-like set
func CalcBarnsleyMandelbrotM2(
	params FractalParameter,
	image Image) {

	stepX, stepY := getSteps(params, image)

	var cy float64 = params.Ymin
	for y := uint(0); y < image.Resolution.Height; y++ {
		var cx float64 = params.Xmin
		for x := uint(0); x < image.Resolution.Width; x++ {
			var zx float64 = cx
			var zy float64 = cy
			var i uint
			for i < params.Maxiter {
				var zxn float64
				var zyn float64
				zx2 := zx * zx
				zy2 := zy * zy
				if zx2+zy2 > float64(params.Bailout) {
					break
				}
				if zx*cy+zy*cx >= 0 {
					zxn = zx*cx - zy*cy - cx
					zyn = zx*cy + zy*cx - cy
				} else {
					zxn = zx*cx - zy*cy + cx
					zyn = zx*cy + zy*cx + cy
				}
				zx = zxn
				zy = zyn
				i++
			}
			image.Z[y][x] = ZPixel(complex(zx, zy))
			image.I[y][x] = IPixel(calcIndex(params, i))
			cx += stepX
		}
		cy += stepY
	}
}

// CalcBarnsleyMandelbrotM3 calculates Barnsley M3 Mandelbrot-like set
func CalcBarnsleyMandelbrotM3(
	params FractalParameter,
	image Image) {

	var cy float64 = -2.0
	for y := uint(0); y < image.Resolution.Height; y++ {
		var cx float64 = -2.0
		for x := uint(0); x < image.Resolution.Width; x++ {
			var zx float64 = cx
			var zy float64 = cy
			var i uint
			for i < params.Maxiter {
				var zxn float64
				var zyn float64
				zx2 := zx * zx
				zy2 := zy * zy
				if zx2+zy2 > float64(params.Bailout) {
					break
				}
				if zx > 0 {
					zxn = zx2 - zy2 - 1
					zyn = 2.0 * zx * zy
				} else {
					zxn = zx2 - zy2 - 1 + cx*zx
					zyn = 2.0*zx*zy + cy*zx
				}
				zx = zxn
				zy = zyn
				i++
			}
			image.Z[y][x] = ZPixel(complex(zx, zy))
			image.I[y][x] = IPixel(calcIndex(params, i))
			cx += 4.0 / float64(image.Resolution.Width)
		}
		cy += 4.0 / float64(image.Resolution.Height)
	}
}

// CalcJuliaFn calculates Julia set into the provided ZPixels
func CalcJuliaFn(
	params FractalParameter,
	image Image) {

	stepX, stepY := getSteps(params, image)

	cx := params.Cx0
	cy := params.Cy0
	var c complex128 = complex(cx, cy)

	var zy0 float64 = params.Ymin
	for y := uint(0); y < image.Resolution.Height; y++ {
		var zx0 float64 = params.Xmin
		for x := uint(0); x < image.Resolution.Width; x++ {
			var z complex128 = complex(zx0, zy0)
			var i uint
			for i < params.Maxiter {
				zx := real(z)
				zy := imag(z)
				if zx*zx+zy*zy > float64(params.Bailout) {
					break
				}
				z = c * cmplx.Sin(z)
				i++
			}
			image.Z[y][x] = ZPixel(z)
			image.I[y][x] = IPixel(calcIndex(params, i))
			zx0 += stepX
		}
		zy0 += stepY
	}
}

// CalcJulia calculates classic Julia fractal
func CalcJulia(
	params FractalParameter,
	image Image) {

	stepX, stepY := getSteps(params, image)

	var zy0 float64 = params.Ymin
	for y := uint(0); y < image.Resolution.Height; y++ {
		var zx0 float64 = params.Xmin
		for x := uint(0); x < image.Resolution.Width; x++ {
			var zx float64 = zx0
			var zy float64 = zy0
			var i uint
			for i < params.Maxiter {
				zx2 := zx * zx
				zy2 := zy * zy
				if zx2+zy2 > float64(params.Bailout) {
					break
				}
				zy = 2.0*zx*zy + params.Cy0
				zx = zx2 - zy2 + params.Cx0
				i++
			}
			image.Z[y][x] = ZPixel(complex(zx, zy))
			image.I[y][x] = IPixel(calcIndex(params, i))
			zx0 += stepX
		}
		zy0 += stepY
	}
}

// CalcJulia calculates Julia fractal for Z=Z^3+c
func CalcJuliaZ3(
	params FractalParameter,
	image Image) {

	stepX, stepY := getSteps(params, image)

	var zy0 float64 = params.Ymin
	for y := uint(0); y < image.Resolution.Height; y++ {
		var zx0 float64 = params.Xmin
		for x := uint(0); x < image.Resolution.Width; x++ {
			var c complex128 = complex(params.Cx0, params.Cy0)
			var z complex128 = complex(zx0, zy0)
			var i uint
			for i < params.Maxiter {
				zx := real(z)
				zy := imag(z)
				if zx*zx+zy*zy > 4.0 {
					break
				}
				z = z*z*z + c
				i++
			}
			image.Z[y][x] = ZPixel(z)
			image.I[y][x] = IPixel(calcIndex(params, i))
			zx0 += stepX
		}
		zy0 += stepY
	}
}

// CalcJulia calculates Julia fractal for Z=Z^4+c
func CalcJuliaZ4(
	params FractalParameter,
	image Image) {

	stepX, stepY := getSteps(params, image)

	var zy0 float64 = params.Ymin
	for y := uint(0); y < image.Resolution.Height; y++ {
		var zx0 float64 = params.Xmin
		for x := uint(0); x < image.Resolution.Width; x++ {
			var c complex128 = complex(params.Cx0, params.Cy0)
			var z complex128 = complex(zx0, zy0)
			var i uint
			for i < params.Maxiter {
				zx := real(z)
				zy := imag(z)
				if zx*zx+zy*zy > 4.0 {
					break
				}
				z = z*z*z*z + c
				i++
			}
			image.Z[y][x] = ZPixel(z)
			image.I[y][x] = IPixel(calcIndex(params, i))
			zx0 += stepX
		}
		zy0 += stepY
	}
}

// CalcMandelLambda calculates Mandelbrot variant of Lambda fractal
func CalcMandelLambda(
	params FractalParameter,
	image Image) {

	stepX, stepY := getSteps(params, image)

	var cy float64 = params.Ymin
	for y := uint(0); y < image.Resolution.Height; y++ {
		var cx float64 = params.Xmin
		for x := uint(0); x < image.Resolution.Width; x++ {
			var c complex128 = complex(cx, cy)
			var z complex128 = complex(params.Cx0, params.Cy0)
			var i uint
			for i < params.Maxiter {
				zx := real(z)
				zy := imag(z)
				if zx*zx+zy*zy > 4.0 {
					break
				}
				z = c * z * (1 - z)
				i++
			}
			image.Z[y][x] = ZPixel(z)
			image.I[y][x] = IPixel(calcIndex(params, i))
			cx += stepX
		}
		cy += stepY
	}
}

// CalcMagnet calculates Magnet Mandelbrot-like set
func CalcMagnet(
	params FractalParameter,
	image Image) {
	const MIN_VALUE = 1.0 - 100

	var cy float64 = -2.0
	for y := uint(0); y < image.Resolution.Height; y++ {
		var cx float64 = -2.0
		for x := uint(0); x < image.Resolution.Width; x++ {
			var zx float64 = params.Cx0
			var zy float64 = params.Cy0
			var i uint
			for i < params.Maxiter {
				var zxn float64
				var zyn float64
				zx2 := zx * zx
				zy2 := zy * zy
				if zx2+zy2 > 100.0 {
					break
				}
				if ((zx-1.0)*(zx-1.0) + zy*zy) < 0.001 {
					break
				}
				tzx := zx2 - zy2 + cx - 1
				tzy := 2.0*zx*zy + cy
				bzx := 2.0*zx + cx - 2
				bzy := 2.0*zy + cy
				div := bzx*bzx + bzy*bzy
				if div < MIN_VALUE {
					break
				}
				zxn = (tzx*bzx + tzy*bzy) / div
				zyn = (tzy*bzx - tzx*bzy) / div
				zx = (zxn + zyn) * (zxn - zyn)
				zy = 2.0 * zxn * zyn
				i++
			}
			image.Z[y][x] = ZPixel(complex(zx, zy))
			image.I[y][x] = IPixel(calcIndex(params, i))
			cx += 4.0 / float64(image.Resolution.Width)
		}
		cy += 4.0 / float64(image.Resolution.Height)
	}
}

// CalcMagnet calculates Magnet Julia-like set
func CalcMagnetJulia(
	params FractalParameter,
	image Image) {
	const MIN_VALUE = 1.0 - 100

	cx := params.Cx0
	cy := params.Cy0
	var zy0 float64 = -2.0
	for y := uint(0); y < image.Resolution.Height; y++ {
		var zx0 float64 = -2.0
		for x := uint(0); x < image.Resolution.Width; x++ {
			var zx float64 = zx0
			var zy float64 = zy0
			var i uint
			for i < params.Maxiter {
				var zxn float64
				var zyn float64
				zx2 := zx * zx
				zy2 := zy * zy
				if zx2+zy2 > 100.0 {
					break
				}
				if ((zx-1.0)*(zx-1.0) + zy*zy) < 0.001 {
					break
				}
				tzx := zx2 - zy2 + cx - 1
				tzy := 2.0*zx*zy + cy
				bzx := 2.0*zx + cx - 2
				bzy := 2.0*zy + cy
				div := bzx*bzx + bzy*bzy
				if div < MIN_VALUE {
					break
				}
				zxn = (tzx*bzx + tzy*bzy) / div
				zyn = (tzy*bzx - tzx*bzy) / div
				zx = (zxn + zyn) * (zxn - zyn)
				zy = 2.0 * zxn * zyn
				i++
			}
			image.Z[y][x] = ZPixel(complex(zx, zy))
			image.I[y][x] = IPixel(calcIndex(params, i))
			zx0 += 4.0 / float64(image.Resolution.Width)
		}
		zy0 += 4.0 / float64(image.Resolution.Height)
	}
}

// CalcMandelbrot calculates Mandelbrot set into the provided ZPixels
func CalcMandelbrot(
	params FractalParameter,
	image Image) {

	stepX, stepY := getSteps(params, image)

	var cy float64 = params.Ymin
	for y := uint(0); y < image.Resolution.Height; y++ {
		var cx float64 = params.Xmin
		for x := uint(0); x < image.Resolution.Width; x++ {
			var zx float64 = params.Cx0
			var zy float64 = params.Cy0
			var i uint
			for i < params.Maxiter {
				zx2 := zx * zx
				zy2 := zy * zy
				if zx2+zy2 > float64(params.Bailout) {
					break
				}
				zy = 2.0*zx*zy + cy
				zx = zx2 - zy2 + cx
				i++
			}
			image.Z[y][x] = ZPixel(complex(zx, zy))
			image.I[y][x] = IPixel(calcIndex(params, i))
			cx += stepX
		}
		cy += stepY
	}
}

// CalcMandelbrotComplex calculates Mandelbrot set into the provided ZPixels
// Calculations use complex numbers
func CalcMandelbrotComplex(
	params FractalParameter,
	image Image) {

	stepX, stepY := getSteps(params, image)

	var cy float64 = params.Ymin
	for y := uint(0); y < image.Resolution.Height; y++ {
		var cx float64 = params.Xmin
		for x := uint(0); x < image.Resolution.Width; x++ {
			c := complex(cx, cy)
			z := complex(params.Cx0, params.Cy0)
			var i uint
			for i < params.Maxiter {
				if cmplx.Abs(z) > float64(params.Bailout) {
					break
				}
				z = z*z + c
				i++
			}
			image.Z[y][x] = ZPixel(z)
			image.I[y][x] = IPixel(calcIndex(params, i))
			cx += stepX
		}
		cy += stepY
	}
}

// CalcMandelbrotZ2pZ calculates Mandelbrot set z=z^2+z+c into the provided ZPixels
// Calculations use complex numbers
func CalcMandelbrotZ2pZ(
	params FractalParameter,
	image Image) {

	var cy float64 = -1.5
	for y := uint(0); y < image.Resolution.Height; y++ {
		var cx float64 = -1.5
		for x := uint(0); x < image.Resolution.Width; x++ {
			var c complex128 = complex(cx, cy)
			var z complex128 = complex(params.Cx0, params.Cy0)
			var i uint
			for i < params.Maxiter {
				zx := real(z)
				zy := imag(z)
				if zx*zx+zy*zy > 4.0 {
					break
				}
				z = z*z + z + c
				i++
			}
			image.Z[y][x] = ZPixel(z)
			image.I[y][x] = IPixel(calcIndex(params, i))
			cx += 3.0 / float64(image.Resolution.Width)
		}
		cy += 3.0 / float64(image.Resolution.Height)
	}
}

// CalcMandelbrotZ2mZ calculates Mandelbrot set z=z^2-z+c into the provided ZPixels
// Calculations use complex numbers
func CalcMandelbrotZ2mZ(
	params FractalParameter,
	image Image) {

	var cy float64 = -1.5
	for y := uint(0); y < image.Resolution.Height; y++ {
		var cx float64 = -1.5
		for x := uint(0); x < image.Resolution.Width; x++ {
			var c complex128 = complex(cx, cy)
			var z complex128 = complex(params.Cx0, params.Cy0)
			var i uint
			for i < params.Maxiter {
				zx := real(z)
				zy := imag(z)
				if zx*zx+zy*zy > 4.0 {
					break
				}
				z = z*z - z + c
				i++
			}
			image.Z[y][x] = ZPixel(z)
			image.I[y][x] = IPixel(calcIndex(params, i))
			cx += 3.0 / float64(image.Resolution.Width)
		}
		cy += 3.0 / float64(image.Resolution.Height)
	}
}

// CalcMandelbrotZ3 calculates Mandelbrot set z=z^3+c into the provided ZPixels
// Calculations use complex numbers
func CalcMandelbrotZ3(
	params FractalParameter,
	image Image) {

	stepX, stepY := getSteps(params, image)

	var cy float64 = params.Ymin
	for y := uint(0); y < image.Resolution.Height; y++ {
		var cx float64 = params.Xmin
		for x := uint(0); x < image.Resolution.Width; x++ {
			var c complex128 = complex(cx, cy)
			var z complex128 = complex(params.Cx0, params.Cy0)
			var i uint
			for i < params.Maxiter {
				zx := real(z)
				zy := imag(z)
				if zx*zx+zy*zy > 4.0 {
					break
				}
				z = z*z*z + c
				i++
			}
			image.Z[y][x] = ZPixel(z)
			image.I[y][x] = IPixel(calcIndex(params, i))
			cx += stepX
		}
		cy += stepY
	}
}

// CalcMandelbrotZ4 calculates Mandelbrot set z=z^4+c into the provided ZPixels
// Calculations use complex numbers
func CalcMandelbrotZ4(
	params FractalParameter,
	image Image) {

	var cy float64 = -1.5
	for y := uint(0); y < image.Resolution.Height; y++ {
		var cx float64 = -1.5
		for x := uint(0); x < image.Resolution.Width; x++ {
			var c complex128 = complex(cx, cy)
			var z complex128 = complex(params.Cx0, params.Cy0)
			var i uint
			for i < params.Maxiter {
				zx := real(z)
				zy := imag(z)
				if zx*zx+zy*zy > 4.0 {
					break
				}
				z = z*z*z*z + c
				i++
			}
			image.Z[y][x] = ZPixel(z)
			image.I[y][x] = IPixel(calcIndex(params, i))
			cx += 3.0 / float64(image.Resolution.Width)
		}
		cy += 3.0 / float64(image.Resolution.Height)
	}
}

// CalcMandelbrotFn calculates Mandelbrot set into the provided ZPixels
func CalcMandelbrotFn(
	params FractalParameter,
	image Image) {

	stepX, stepY := getSteps(params, image)

	var cy float64 = params.Ymin
	for y := uint(0); y < image.Resolution.Height; y++ {
		var cx float64 = params.Xmin
		for x := uint(0); x < image.Resolution.Width; x++ {
			c := complex(cx, cy)
			z := c
			var i uint
			for i < params.Maxiter {
				zx := real(z)
				zy := imag(z)
				if zx*zx+zy*zy > float64(params.Bailout) {
					break
				}
				z = c * cmplx.Sin(z)
				i++
			}
			image.Z[y][x] = ZPixel(z)
			image.I[y][x] = IPixel(i)
			cx += stepX
		}
		cy += stepY
	}
}

// main function
func main() {
	fmt.Println("1000 lines of Go")
}

//
// finito
//
