/*
 This file is part of 'TuiView' - a simple Raster viewer
 Copyright (C) 2012  Sam Gillingham

 This program is free software; you can redistribute it and/or
 modify it under the terms of the GNU General Public License
 as published by the Free Software Foundation; either version 2
 of the License, or (at your option) any later version.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program; if not, write to the Free Software
 Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
*/

#include <Python.h>
#include "numpy/arrayobject.h"
#include <string.h>
#include <stdlib.h>

#include "ogr_api.h"

/* define WKB_BYTE_ORDER depending on endian setting
 from pyconfig.h */
#if WORDS_BIGENDIAN == 1
    #define WKB_BYTE_ORDER wkbXDR
#else
    #define WKB_BYTE_ORDER wkbNDR
#endif

/* do a memcpy rather than cast and access so we work on SPARC etc with aligned reads */
#define READ_WKB_VAL(n, p)  memcpy(&n, p, sizeof(n)); p += sizeof(n);

/* for buring points as a cross so they can be seen */
#define HALF_CROSS_SIZE 5

typedef struct 
{
    PyArrayObject *pArray;
    int nLineWidth;
    double *pExtents;
    double dMetersPerPix;
    npy_intp nXSize;
    npy_intp nYSize;
    int bFill;
} VectorWriterData;

static VectorWriterData* VectorWriter_create(PyArrayObject *pArray, double *pExtents, 
        int nLineWidth, int bFill)
{
    VectorWriterData *pData;

    pData = (VectorWriterData*)malloc(sizeof(VectorWriterData));

    pData->pArray = pArray;
    pData->pExtents = pExtents;
    pData->nLineWidth = nLineWidth;
    if( pData->nLineWidth < 1 ) /* hack necessary? */
        pData->nLineWidth = 1;
    pData->nYSize = PyArray_DIMS(pArray)[0];
    pData->nXSize = PyArray_DIMS(pArray)[1];
    pData->dMetersPerPix = (pExtents[2] - pExtents[0]) / ((double)pData->nXSize);
    pData->bFill = bFill;

    return pData;
}

static void VectorWriter_destroy(VectorWriterData *pData)
{
    free(pData);
}

static void VectorWriter_plot(VectorWriterData *pData, int x, int y)
{
    /*fprintf(stderr, "plot %d %d\n", x, y);*/
    double dSize;
    int nNorthWestPixels, nSouthEastPixels;
    int tlx, tly, brx, bry;

    if( pData->nLineWidth == 1 )
    {
        if( ( x >= 0 ) && ( x < pData->nXSize ) && ( y >= 0 ) && ( y < pData->nYSize ) )
        {
            *((npy_uint8*)PyArray_GETPTR2(pData->pArray, y, x)) = 1;
        }
    }
    else
    {
        /* do some dodgy maths to work out how many pixels either side
         since if it is an even number we err to the north west*/
        dSize = ((double)(pData->nLineWidth-1)) / 2.0;
        nNorthWestPixels = ceil(dSize);
        nSouthEastPixels = floor(dSize);
        tlx = x - nNorthWestPixels;
        tly = y - nNorthWestPixels;
        brx = x + nSouthEastPixels;
        bry = y + nSouthEastPixels;
        for( x = tlx; x <= brx; x++ )
        {
            for( y = tly; y <= bry; y++ )
            {
                if( ( x >= 0 ) && ( x < pData->nXSize ) && ( y >= 0 ) && ( y < pData->nYSize ) )
                {
                    *((npy_uint8*)PyArray_GETPTR2(pData->pArray, y, x)) = 1;
                }
            }
        }
    }
}

/* adapted from http://roguebasin.roguelikedevelopment.org/index.php?title=Bresenham%27s_Line_Algorithm#C.2B.2B */
static void VectorWriter_bresenham(VectorWriterData *pData, int x1, int y1, int x2, int y2)
{
    int delta_x, delta_y, error;
    signed char ix, iy;

    delta_x = x2 - x1;
    /* if x1 == x2, then it does not matter what we set here*/
    ix = (delta_x > 0) - (delta_x < 0);
    delta_x = abs(delta_x) << 1;
 
    delta_y = y2 - y1;
    /* if y1 == y2, then it does not matter what we set here*/
    iy = (delta_y > 0) - (delta_y < 0);
    delta_y = abs(delta_y) << 1;
 
    VectorWriter_plot(pData, x1, y1);
 
    if (delta_x >= delta_y)
    {
        /* error may go below zero*/
        error = delta_y - (delta_x >> 1);
 
        while (x1 != x2)
        {
            if ((error >= 0) && (error || (ix > 0)))
            {
                error -= delta_x;
                y1 += iy;
            }
            /* else do nothing*/
 
            error += delta_y;
            x1 += ix;
 
            VectorWriter_plot(pData, x1, y1);
        }
    }
    else
    {
        /* error may go below zero*/
        error = delta_x - (delta_y >> 1);
 
        while (y1 != y2)
        {
            if ((error >= 0) && (error || (iy > 0)))
            {
                error -= delta_y;
                x1 += ix;
            }
            /* else do nothing*/
 
            error += delta_x;
            y1 += iy;
 
            VectorWriter_plot(pData, x1, y1);
        }
    }
}

static void VectorWriter_burnPoint(VectorWriterData *pData, double dx, double dy)
{
    int nx, ny, x, y;

    nx = (dx - pData->pExtents[0]) / pData->dMetersPerPix;
    ny = (pData->pExtents[1] - dy) / pData->dMetersPerPix;
    /* burn a cross*/
    for( x = (nx - HALF_CROSS_SIZE); x < (nx + HALF_CROSS_SIZE); x++)
        VectorWriter_plot(pData, x, ny);
    for( y = (ny - HALF_CROSS_SIZE); y < (ny + HALF_CROSS_SIZE); y++)
        VectorWriter_plot(pData, nx, y);
}

static void VectorWriter_burnLine(VectorWriterData *pData, double dx1, double dy1, double dx2, double dy2)
{
    int nx1, ny1, nx2, ny2;

    nx1 = (dx1 - pData->pExtents[0]) / pData->dMetersPerPix;
    ny1 = (pData->pExtents[1] - dy1) / pData->dMetersPerPix;
    nx2 = (dx2 - pData->pExtents[0]) / pData->dMetersPerPix;
    ny2 = (pData->pExtents[1] - dy2) / pData->dMetersPerPix;
    VectorWriter_bresenham(pData, nx1, ny1, nx2, ny2);
}

static unsigned char* VectorWriter_processPoint(VectorWriterData *pData, unsigned char *pWKB, int hasz)
{
    double x, y;

    READ_WKB_VAL(x, pWKB)
    READ_WKB_VAL(y, pWKB)
    if(hasz)
    {
        pWKB += sizeof(double);
    }

    VectorWriter_burnPoint(pData, x, y);
    return pWKB;
}

static unsigned char* VectorWriter_processLineString(VectorWriterData *pData, unsigned char *pWKB, int hasz)
{
    GUInt32 nPoints, n;
    double dx1, dy1, dx2, dy2;

    READ_WKB_VAL(nPoints, pWKB)
    if( nPoints > 0 )
    {
        /* get the first point */
        READ_WKB_VAL(dx1, pWKB)
        READ_WKB_VAL(dy1, pWKB)
        if(hasz)
        {
            pWKB += sizeof(double);
        }
        for( n = 1; n < nPoints; n++ )
        {
            READ_WKB_VAL(dx2, pWKB)
            READ_WKB_VAL(dy2, pWKB)
            if(hasz)
            {
                pWKB += sizeof(double);
            }
            VectorWriter_burnLine(pData, dx1, dy1, dx2, dy2);
            /* set up for next one */
            dx1 = dx2;
            dy1 = dy2;
        }
    }
    return pWKB;
}

/* See http://alienryderflex.com/polygon/ */
void precalc_values(int polyCorners, double *polyX, double *polyY, double *constant, double *multiple)
{
  int i, j=polyCorners-1;

    for(i=0; i<polyCorners; i++) 
    {
        if(polyY[j]==polyY[i]) 
        {
            constant[i]=polyX[i];
            multiple[i]=0; 
        }
        else 
        {
            constant[i]=polyX[i]-(polyY[i]*polyX[j])/(polyY[j]-polyY[i])+(polyY[i]*polyX[i])/(polyY[j]-polyY[i]);
            multiple[i]=(polyX[j]-polyX[i])/(polyY[j]-polyY[i]); 
        }
        j=i; 
    }
}

int pointInPolygon(int polyCorners, double x, double y,double *polyX, 
        double *polyY, double *constant, double *multiple) 
{
    int   i, j=polyCorners-1;
    int  oddNodes=0;

    for (i=0; i<polyCorners; i++) 
    {
        if ((((polyY[i]< y) && (polyY[j]>=y))
            ||   ((polyY[j]< y) && (polyY[i]>=y))) )
        {
            oddNodes^=(y*multiple[i]+constant[i]<x); 
        }
        j=i; 
    }

    return oddNodes; 
}

/* same as processLineString, but closes ring */
static unsigned char* VectorWriter_processLinearRing(VectorWriterData *pData, unsigned char *pWKB, int hasz)
{
    GUInt32 nPoints, n;
    double dx1, dy1, dx2, dy2;
    double dFirstX, dFirstY;
    /* when pData->bFill */
    double *pPolyX, *pPolyY, *pConstant, *pMultiple;
    double dMinX, dMaxX, dMinY, dMaxY;
    int x, y;

    READ_WKB_VAL(nPoints, pWKB)
    if( nPoints > 0 )
    {
        if( pData->bFill )
        {
            pPolyX = (double*)malloc(nPoints * sizeof(double));
            pPolyY = (double*)malloc(nPoints * sizeof(double));
            pConstant = (double*)malloc(nPoints * sizeof(double));
            pMultiple = (double*)malloc(nPoints * sizeof(double));

            for( n = 0; n < nPoints; n++ )
            {
                READ_WKB_VAL(dx1, pWKB)
                READ_WKB_VAL(dy1, pWKB)
                if(hasz)
                {
                    pWKB += sizeof(double);
                }
                pPolyX[n] = dx1;
                pPolyY[n] = dy1;
                /* need the extent */
                if( n == 0 )
                {
                    dMinX = dx1;
                    dMaxX = dx1;
                    dMinY = dy1;
                    dMaxY = dy1;
                }
                else
                {
                    if( dx1 < dMinX )
                        dMinX = dx1;
                    else if( dx1 > dMaxX)
                        dMaxX = dx1;
                    else if( dy1 < dMinY)
                        dMinY = dy1;
                    else if( dy1 > dMaxY)
                        dMaxY = dy1;
                }
            }

            /* if we are not actually anywhere near the extent then just return */
            if( ( dMinX > pData->pExtents[2] ) || ( dMaxX < pData->pExtents[0])
                    || (dMinY > pData->pExtents[1] ) || (dMaxY < pData->pExtents[3]) )
            {
                /*fprintf( stderr, "ignoring poly %d %d %d %d\n", ( dMinX > pData->pExtents[2] ), ( dMaxX < pData->pExtents[0]), 
                        (dMinY > pData->pExtents[1] ) , (dMaxY > pData->pExtents[3]));*/
                return pWKB;
            }

            precalc_values(nPoints, pPolyX, pPolyY, pConstant, pMultiple);

            /* pData->pExtents is (tlx, tly, brx, bry) */
            /* chop down area to that within the extent */
            if( dMinX < pData->pExtents[0] )
                dMinX = pData->pExtents[0];
            if( dMaxX > pData->pExtents[2] )
                dMaxX = pData->pExtents[2];
            if( dMinY < pData->pExtents[3] )
                dMinY = pData->pExtents[3];
            if( dMaxY > pData->pExtents[1] )
                dMaxY = pData->pExtents[1];

            for( dy1 = dMaxY; dy1 > dMinY; dy1 -= pData->dMetersPerPix )
            {
                for( dx1 = dMinX; dx1 < dMaxX; dx1 += pData->dMetersPerPix )
                {
                    if( pointInPolygon(nPoints, dx1, dy1, pPolyX, pPolyY,
                            pConstant, pMultiple) )
                    {
                        x = (dx1 - pData->pExtents[0]) / pData->dMetersPerPix;
                        y = (pData->pExtents[1] - dy1) / pData->dMetersPerPix;
                        VectorWriter_plot(pData, x, y);
                    }
                }
            }

            free(pPolyX);
            free(pPolyY);
            free(pConstant);
            free(pMultiple);
        }
        else
        {
            /* outline */
            /* get the first point */
            READ_WKB_VAL(dx1, pWKB)
            READ_WKB_VAL(dy1, pWKB)
            if(hasz)
            {
                pWKB += sizeof(double);
            }
            dFirstX = dx1;
            dFirstY = dy1;

            for( n = 1; n < nPoints; n++ )
            {
                READ_WKB_VAL(dx2, pWKB)
                READ_WKB_VAL(dy2, pWKB)
                if(hasz)
                {
                    pWKB += sizeof(double);
                }
                VectorWriter_burnLine(pData, dx1, dy1, dx2, dy2);

                /* set up for next one */
                dx1 = dx2;
                dy1 = dy2;
            }
            /* close it*/
            VectorWriter_burnLine(pData, dx1, dy1, dFirstX, dFirstY);
        }
    }
    return pWKB;
}

static unsigned char* VectorWriter_processPolygon(VectorWriterData *pData, unsigned char *pWKB, int hasz)
{
    GUInt32 nRings, n;

    READ_WKB_VAL(nRings, pWKB)
    for( n = 0; n < nRings; n++ )
    {
        pWKB = VectorWriter_processLinearRing(pData, pWKB, hasz);
    }
    return pWKB;
}

static unsigned char* VectorWriter_processMultiPoint(VectorWriterData *pData, unsigned char *pWKB, int hasz)
{
    GUInt32 nPoints, n;

    READ_WKB_VAL(nPoints, pWKB)
    for( n = 0; n < nPoints; n++ )
    {
        pWKB++; /* ignore endian */
        pWKB += sizeof(GUInt32); /* ignore type (must be point) */
        pWKB = VectorWriter_processPoint(pData, pWKB, hasz);
    }
    return pWKB;
}

static unsigned char* VectorWriter_processMultiLineString(VectorWriterData *pData, unsigned char *pWKB, int hasz)
{
    GUInt32 nLines, n;

    READ_WKB_VAL(nLines, pWKB)
    for( n = 0; n < nLines; n++ )
    {
        pWKB++; /* ignore endian */
        pWKB += sizeof(GUInt32); /* ignore type */
        pWKB = VectorWriter_processLineString(pData, pWKB, hasz);
    }
    return pWKB;
}

static unsigned char* VectorWriter_processMultiPolygon(VectorWriterData *pData, unsigned char *pWKB, int hasz)
{
    GUInt32 nPolys, n;

    READ_WKB_VAL(nPolys, pWKB)
    for( n = 0; n < nPolys; n++ )
    {
        pWKB++; /* ignore endian */
        pWKB += sizeof(GUInt32); /* ignore type */
        pWKB = VectorWriter_processPolygon(pData, pWKB, hasz);
    }
    return pWKB;
}

static unsigned char* VectorWriter_processWKB(VectorWriterData *pData, unsigned char *pCurrWKB);

static unsigned char* VectorWriter_processGeometryCollection(VectorWriterData *pData, unsigned char *pWKB)
{
    GUInt32 nGeoms, n;

    READ_WKB_VAL(nGeoms, pWKB)
    for( n = 0; n < nGeoms; n++ )
    {
        /* start again! */
        pWKB = VectorWriter_processWKB(pData, pWKB);
    }
    return pWKB;
}

static unsigned char* VectorWriter_processWKB(VectorWriterData *pData, unsigned char *pCurrWKB)
{
    GUInt32 nType;

    /* ignore byte order (should be native) */
    pCurrWKB++;
    READ_WKB_VAL(nType, pCurrWKB)
    switch(nType)
    {
    case wkbPoint:
        pCurrWKB = VectorWriter_processPoint(pData, pCurrWKB, 0);
        break;
    case wkbPoint25D:
        pCurrWKB = VectorWriter_processPoint(pData, pCurrWKB, 1);
        break;
    case wkbLineString:
        pCurrWKB = VectorWriter_processLineString(pData, pCurrWKB, 0);
        break;
    case wkbLineString25D:
        pCurrWKB = VectorWriter_processLineString(pData, pCurrWKB, 1);
        break;
    case wkbPolygon:
        pCurrWKB = VectorWriter_processPolygon(pData, pCurrWKB, 0);
        break;
    case wkbPolygon25D:
        pCurrWKB = VectorWriter_processPolygon(pData, pCurrWKB, 1);
        break;
    case wkbMultiPoint:
        pCurrWKB = VectorWriter_processMultiPoint(pData, pCurrWKB, 0);
        break;
    case wkbMultiPoint25D:
        pCurrWKB = VectorWriter_processMultiPoint(pData, pCurrWKB, 1);
        break;
    case wkbMultiLineString:
        pCurrWKB = VectorWriter_processMultiLineString(pData, pCurrWKB, 0);
        break;
    case wkbMultiLineString25D:
        pCurrWKB = VectorWriter_processMultiLineString(pData, pCurrWKB, 1);
        break;
    case wkbMultiPolygon:
        pCurrWKB = VectorWriter_processMultiPolygon(pData, pCurrWKB, 0);
        break;
    case wkbMultiPolygon25D:
        pCurrWKB = VectorWriter_processMultiPolygon(pData, pCurrWKB, 1);
        break;
    case wkbGeometryCollection:
    case wkbGeometryCollection25D:
        pCurrWKB = VectorWriter_processGeometryCollection(pData, pCurrWKB);
        break;
    case wkbNone:
        /* pure attribute records */
        break;
    default:
        fprintf( stderr, "Unknown WKB code %d\n", nType);
        break;
    }
    return pCurrWKB;
}

/* bit of a hack here - this is what a SWIG object looks
 like. It is only defined in the source file so we copy it here*/
typedef struct {
  PyObject_HEAD
  void *ptr;
  /* the rest aren't needed (and a hassle to define here)
  swig_type_info *ty;
  int own;
  PyObject *next;*/
} SwigPyObject;

/* in the ideal world I would use SWIG_ConvertPtr etc
 but to avoid the whole dependence on SWIG headers
 and needing to reach into the GDAL source to get types etc
 I happen to know the 'this' attribute is a pointer to 
 OGRLayerShadow which is actually a pointer
 to a SwigPyObject whose ptr field is a pointer to a
 OGRLayer. Phew. 
 Given a python object this function returns the underlying
 pointer. Returns NULL on failure (exception string already set)*/
void *getUnderlyingPtrFromSWIGPyObject(PyObject *pObj, PyObject *pException)
{
    PyObject *pThisAttr; /* the 'this' field */
    SwigPyObject *pSwigThisAttr;
    void *pUnderlying;

    pThisAttr = PyObject_GetAttrString(pObj, "this");
    if( pThisAttr == NULL )
    {
        PyErr_SetString(pException, "object does not appear to be a swig type");
        return NULL;
    }

    /* i think it is safe to do this since pObj is still around*/
    Py_DECREF(pThisAttr);

    /* convert this to a SwigPyObject*/
    pSwigThisAttr = (SwigPyObject*)pThisAttr;

    /* get the ptr field*/
    pUnderlying = pSwigThisAttr->ptr;
    if( pUnderlying == NULL )
    {
        PyErr_SetString(pException, "underlying object is NULL");
        return NULL;
    }

    return pUnderlying;
}


/* An exception object for this module */
/* created in the init function */
struct VectorRasterizerState
{
    PyObject *error;
};

#if PY_MAJOR_VERSION >= 3
#define GETSTATE(m) ((struct VectorRasterizerState*)PyModule_GetState(m))
#else
#define GETSTATE(m) (&_state)
static struct VectorRasterizerState _state;
#endif


static PyObject *vectorrasterizer_rasterizeLayer(PyObject *self, PyObject *args)
{
    PyObject *pPythonLayer; /* of type ogr.Layer*/
    PyObject *pBBoxObject; /* must be a sequence*/
    int nXSize, nYSize, nLineWidth;
    const char *pszSQLFilter;
    void *pPtr;
    OGRLayerH hOGRLayer;
    double adExtents[4];
    PyObject *o, *pOutArray;
    npy_intp dims[2];
    VectorWriterData *pWriter;
    OGRFeatureH hFeature;
    int nCurrWKBSize;
    unsigned char *pCurrWKB;
    OGRGeometryH hGeometry;
    int nNewWKBSize;
    unsigned char *pNewWKB;
    int n, bFill = 0;

    if( !PyArg_ParseTuple(args, "OOiiiz|i:rasterizeLayer", &pPythonLayer, 
            &pBBoxObject, &nXSize, &nYSize, &nLineWidth, &pszSQLFilter, &bFill))
        return NULL;

    pPtr = getUnderlyingPtrFromSWIGPyObject(pPythonLayer, GETSTATE(self)->error);
    if( pPtr == NULL )
        return NULL;
    hOGRLayer = (OGRLayerH)pPtr;

    if( !PySequence_Check(pBBoxObject))
    {
        PyErr_SetString(GETSTATE(self)->error, "second argument must be a sequence");
        return NULL;
    }

    if( PySequence_Size(pBBoxObject) != 4 )
    {
        PyErr_SetString(GETSTATE(self)->error, "sequence must have 4 elements");
        return NULL;
    }

    for( n = 0; n < 4; n++ )
    {
        o = PySequence_GetItem(pBBoxObject, n);
        if( !PyFloat_Check(o) )
        {
            PyErr_SetString(GETSTATE(self)->error, "Must be a sequence of floats" );
            Py_DECREF(o);
            return NULL;
        }
        adExtents[n] = PyFloat_AsDouble(o);
        Py_DECREF(o);
    }

    /* create output array - all 0 to begin with */
    dims[0] = nYSize;
    dims[1] = nXSize;
    pOutArray = PyArray_ZEROS(2, dims, NPY_UINT8, 0);
    if( pOutArray == NULL )
    {
        PyErr_SetString(GETSTATE(self)->error, "Unable to allocate array" );
        return NULL;
    }

    /* set up the object that does the writing */
    pWriter = VectorWriter_create((PyArrayObject*)pOutArray, adExtents, nLineWidth, bFill);
    
    /* set the spatial filter to the extent */
    OGR_L_SetSpatialFilterRect(hOGRLayer, adExtents[0], adExtents[1], adExtents[2], adExtents[3]);
    /* set the attribute filter (if None/NULL resets) */
    OGR_L_SetAttributeFilter(hOGRLayer, pszSQLFilter);

    OGR_L_ResetReading(hOGRLayer);

    nCurrWKBSize = 0;
    pCurrWKB = NULL;

    while( ( hFeature = OGR_L_GetNextFeature(hOGRLayer)) != NULL )
    {
        hGeometry = OGR_F_GetGeometryRef(hFeature);
        if( hGeometry != NULL )
        {
            /* how big a buffer do we need? Grow if needed */
            nNewWKBSize = OGR_G_WkbSize(hGeometry);
            if( nNewWKBSize > nCurrWKBSize )
            {
                pNewWKB = (unsigned char*)realloc(pCurrWKB, nNewWKBSize);
                if( pNewWKB == NULL )
                {
                    /* realloc failed - bail out */
                    /* according to man page original not freed */
                    free(pCurrWKB);
                    Py_DECREF(pOutArray);
                    OGR_F_Destroy(hFeature);
                    VectorWriter_destroy(pWriter);
                    PyErr_SetString(GETSTATE(self)->error, "memory allocation failed");
                    return NULL;
                }
                else
                {
                    pCurrWKB = pNewWKB;
                    nCurrWKBSize = nNewWKBSize;
                }
            }
            /* read it in */
            OGR_G_ExportToWkb(hGeometry, WKB_BYTE_ORDER, pCurrWKB);
            /* write it to array */
            VectorWriter_processWKB(pWriter, pCurrWKB);
        }

        OGR_F_Destroy(hFeature);
    }
    free( pCurrWKB );
    VectorWriter_destroy(pWriter);

    return pOutArray;
}

static PyObject *vectorrasterizer_rasterizeFeature(PyObject *self, PyObject *args)
{
    PyObject *pPythonFeature; /* of type ogr.Feature*/
    PyObject *pBBoxObject; /* must be a sequence*/
    int nXSize, nYSize, nLineWidth;
    void *pPtr;
    OGRFeatureH hOGRFeature;
    double adExtents[4];
    PyObject *o;
    npy_intp dims[2];
    PyObject *pOutArray;
    VectorWriterData *pWriter;
    OGRGeometryH hGeometry;
    int nNewWKBSize;
    unsigned char *pCurrWKB;
    int n, bFill = 0;

    if( !PyArg_ParseTuple(args, "OOiii|i:rasterizeFeature", &pPythonFeature, 
            &pBBoxObject, &nXSize, &nYSize, &nLineWidth, &bFill))
        return NULL;

    pPtr = getUnderlyingPtrFromSWIGPyObject(pPythonFeature, GETSTATE(self)->error);
    if( pPtr == NULL )
        return NULL;
    hOGRFeature = (OGRFeatureH)pPtr;

    if( !PySequence_Check(pBBoxObject))
    {
        PyErr_SetString(GETSTATE(self)->error, "second argument must be a sequence");
        return NULL;
    }

    if( PySequence_Size(pBBoxObject) != 4 )
    {
        PyErr_SetString(GETSTATE(self)->error, "sequence must have 4 elements");
        return NULL;
    }

    for( n = 0; n < 4; n++ )
    {
        o = PySequence_GetItem(pBBoxObject, n);
        if( !PyFloat_Check(o) )
        {
            PyErr_SetString(GETSTATE(self)->error, "Must be a sequence of floats" );
            Py_DECREF(o);
            return NULL;
        }
        adExtents[n] = PyFloat_AsDouble(o);
        Py_DECREF(o);
    }

    /* create output array - all 0 to begin with */
    dims[0] = nYSize;
    dims[1] = nXSize;
    pOutArray = PyArray_ZEROS(2, dims, NPY_UINT8, 0);
    if( pOutArray == NULL )
    {
        PyErr_SetString(GETSTATE(self)->error, "Unable to allocate array" );
        return NULL;
    }

    /* set up the object that does the writing */
    pWriter = VectorWriter_create((PyArrayObject*)pOutArray, adExtents, nLineWidth, bFill);
    
    hGeometry = OGR_F_GetGeometryRef(hOGRFeature);
    if( hGeometry != NULL )
    {
        /* how big a buffer do we need? */
        nNewWKBSize = OGR_G_WkbSize(hGeometry);
        pCurrWKB = (unsigned char*)malloc(nNewWKBSize);
        if( pCurrWKB == NULL )
        {
            /* malloc failed - bail out*/
            Py_DECREF(pOutArray);
            VectorWriter_destroy(pWriter);
            PyErr_SetString(GETSTATE(self)->error, "memory allocation failed");
            return NULL;
        }
        else
        {
            /* read it in*/
            OGR_G_ExportToWkb(hGeometry, WKB_BYTE_ORDER, pCurrWKB);
            /* write it to array*/
            VectorWriter_processWKB(pWriter, pCurrWKB);
            free( pCurrWKB );
        }
    }
    VectorWriter_destroy(pWriter);

    return pOutArray;
}

static PyObject *vectorrasterizer_rasterizeGeometry(PyObject *self, PyObject *args)
{
    PyObject *pPythonGeometry; /* of type ogr.Geometry*/
    PyObject *pBBoxObject; /* must be a sequence*/
    int nXSize, nYSize, nLineWidth;
    void *pPtr;
    double adExtents[4];
    PyObject *o;
    npy_intp dims[2];
    PyObject *pOutArray;
    VectorWriterData *pWriter;
    OGRGeometryH hGeometry;
    int nNewWKBSize;
    unsigned char *pCurrWKB;
    int n, bFill = 0;

    if( !PyArg_ParseTuple(args, "OOiii|i:rasterizeGeometry", &pPythonGeometry, 
            &pBBoxObject, &nXSize, &nYSize, &nLineWidth, &bFill))
        return NULL;

    pPtr = getUnderlyingPtrFromSWIGPyObject(pPythonGeometry, GETSTATE(self)->error);
    if( pPtr == NULL )
        return NULL;
    hGeometry = (OGRGeometryH)pPtr;

    if( !PySequence_Check(pBBoxObject))
    {
        PyErr_SetString(GETSTATE(self)->error, "second argument must be a sequence");
        return NULL;
    }

    if( PySequence_Size(pBBoxObject) != 4 )
    {
        PyErr_SetString(GETSTATE(self)->error, "sequence must have 4 elements");
        return NULL;
    }

    for( n = 0; n < 4; n++ )
    {
        o = PySequence_GetItem(pBBoxObject, n);
        if( !PyFloat_Check(o) )
        {
            PyErr_SetString(GETSTATE(self)->error, "Must be a sequence of floats" );
            Py_DECREF(o);
            return NULL;
        }
        adExtents[n] = PyFloat_AsDouble(o);
        Py_DECREF(o);
    }

    /* create output array - all 0 to begin with */
    dims[0] = nYSize;
    dims[1] = nXSize;
    pOutArray = PyArray_ZEROS(2, dims, NPY_UINT8, 0);
    if( pOutArray == NULL )
    {
        PyErr_SetString(GETSTATE(self)->error, "Unable to allocate array" );
        return NULL;
    }

    /* set up the object that does the writing */
    pWriter = VectorWriter_create((PyArrayObject*)pOutArray, adExtents, nLineWidth, bFill);
    
    if( hGeometry != NULL )
    {
        /* how big a buffer do we need? */
        nNewWKBSize = OGR_G_WkbSize(hGeometry);
        pCurrWKB = (unsigned char*)malloc(nNewWKBSize);
        if( pCurrWKB == NULL )
        {
            /* malloc failed - bail out*/
            Py_DECREF(pOutArray);
            VectorWriter_destroy(pWriter);
            PyErr_SetString(GETSTATE(self)->error, "memory allocation failed");
            return NULL;
        }
        else
        {
            /* read it in*/
            OGR_G_ExportToWkb(hGeometry, WKB_BYTE_ORDER, pCurrWKB);
            /* write it to array*/
            VectorWriter_processWKB(pWriter, pCurrWKB);
            free( pCurrWKB );
        }
    }
    VectorWriter_destroy(pWriter);

    return pOutArray;
}

/* Our list of functions in this module*/
static PyMethodDef VectorRasterizerMethods[] = {
    {"rasterizeLayer", vectorrasterizer_rasterizeLayer, METH_VARARGS, 
"read an OGR dataset and vectorize outlines to numpy array:\n"
"call signature: arr = rasterizeOutlines(ogrlayer, boundingbox, xsize, ysize, linewidth, sql, fill=False)\n"
"where:\n"
"  ogrlayer is an instance of ogr.Layer\n"
"  boundingbox is a sequence that contains (tlx, tly, brx, bry)\n"
"  xsize,ysize size of output array\n"
"  linewidth is the width of the line\n"
"  sql is the attribute filter. Pass None or SQL string\n"
"  fill is an optional argument that determines if polygons are filled in"},
    {"rasterizeFeature", vectorrasterizer_rasterizeFeature, METH_VARARGS, 
"read an OGR feature and vectorize outlines to numpy array:\n"
"call signature: arr = rasterizeFeature(ogrfeature, boundingbox, xsize, ysize, fill=False)\n"
"where:\n"
"  ogrfeature is an instance of ogr.Feature\n"
"  boundingbox is a sequence that contains (tlx, tly, brx, bry, linewidth)\n"
"  xsize,ysize size of output array\n"
"  linewidth is the width of the line\n"
"  fill is an optional argument that determines if polygons are filled in\n"},
    {"rasterizeGeometry", vectorrasterizer_rasterizeGeometry, METH_VARARGS,
"read an OGR Geometry and vectorize outlines to numpy array:\n"
"call signature: arr = rasterizeGeometry(ogrgeometry, boundingbox, xsize, ysize, fill=False)\n"
"where:\n"
"  ogrgeometry is an instance of ogr.Geometry\n"
"  boundingbox is a sequence that contains (tlx, tly, brx, bry, linewidth)\n"
"  xsize,ysize size of output array\n"
"  linewidth is the width of the line\n"
"  fill is an optional argument that determines if polygons are filled in\n"},
    {NULL}        /* Sentinel */
};

#if PY_MAJOR_VERSION >= 3

static int vectorrasterizer_traverse(PyObject *m, visitproc visit, void *arg) 
{
    Py_VISIT(GETSTATE(m)->error);
    return 0;
}

static int vectorrasterizer_clear(PyObject *m) 
{
    Py_CLEAR(GETSTATE(m)->error);
    return 0;
}

static struct PyModuleDef moduledef = {
        PyModuleDef_HEAD_INIT,
        "vectorrasterizer",
        NULL,
        sizeof(struct VectorRasterizerState),
        VectorRasterizerMethods,
        NULL,
        vectorrasterizer_traverse,
        vectorrasterizer_clear,
        NULL
};

#define INITERROR return NULL

PyMODINIT_FUNC 
PyInit_vectorrasterizer(void)

#else
#define INITERROR return

PyMODINIT_FUNC
initvectorrasterizer(void)
#endif
{
    PyObject *pModule;
    struct VectorRasterizerState *state;

    /* initialize the numpy stuff */
    import_array();

#if PY_MAJOR_VERSION >= 3
    pModule = PyModule_Create(&moduledef);
#else
    pModule = Py_InitModule("vectorrasterizer", VectorRasterizerMethods);
#endif
    if( pModule == NULL )
        INITERROR;

    state = GETSTATE(pModule);

    /* Create and add our exception type */
    state->error = PyErr_NewException("vectorrasterizer.error", NULL, NULL);
    if( state->error == NULL )
    {
        Py_DECREF(pModule);
        INITERROR;
    }
    PyModule_AddObject(pModule, "error", state->error);

#if PY_MAJOR_VERSION >= 3
    return pModule;
#endif
}
