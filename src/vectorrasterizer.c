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

#define PY_SSIZE_T_CLEAN
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

/* for burning points as a cross so they can be seen */
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
    int nHalfCrossSize;
    npy_uint8 nValueToBurn;
} VectorWriterData;

static VectorWriterData* VectorWriter_create(PyArrayObject *pArray, double *pExtents, 
        int nLineWidth, int bFill, int nHalfCrossSize)
{
    VectorWriterData *pData;

    pData = (VectorWriterData*)malloc(sizeof(VectorWriterData));

    pData->pArray = pArray;
    pData->pExtents = pExtents;
    pData->nLineWidth = nLineWidth;
    pData->nYSize = PyArray_DIMS(pArray)[0];
    pData->nXSize = PyArray_DIMS(pArray)[1];
    pData->dMetersPerPix = (pExtents[2] - pExtents[0]) / ((double)pData->nXSize);
    pData->bFill = bFill;
    pData->nHalfCrossSize = nHalfCrossSize;
    pData->nValueToBurn = 1;
    
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
            *((npy_uint8*)PyArray_GETPTR2(pData->pArray, y, x)) = pData->nValueToBurn;
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
                    *((npy_uint8*)PyArray_GETPTR2(pData->pArray, y, x)) = pData->nValueToBurn;
                }
            }
        }
    }
}

/* Like VectorWriter_plot but always plots even if nLineWidth == 0 */
/* For use in filling a poly */
static inline void VectorWriter_plot_for_fill(VectorWriterData *pData, int x, int y)
{
    if( ( x >= 0 ) && ( x < pData->nXSize ) && ( y >= 0 ) && ( y < pData->nYSize ) )
    {
        *((npy_uint8*)PyArray_GETPTR2(pData->pArray, y, x)) = pData->nValueToBurn;
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
    if( pData->nHalfCrossSize == 0 )
    {
        VectorWriter_plot(pData, nx, ny);
    }
    else if( pData->nHalfCrossSize > 0 )
    {
        /* burn a cross*/
        for( x = (nx - pData->nHalfCrossSize); x < (nx + pData->nHalfCrossSize); x++)
            VectorWriter_plot(pData, x, ny);
        for( y = (ny - pData->nHalfCrossSize); y < (ny + pData->nHalfCrossSize); y++)
            VectorWriter_plot(pData, nx, y);
    }
}

static void VectorWriter_burnLine(VectorWriterData *pData, double dx1, double dy1, double dx2, double dy2)
{
    int nx1, ny1, nx2, ny2;

    /* note: not round as that can pop it into the neihbouring pixel */
    nx1 = (dx1 - pData->pExtents[0]) / pData->dMetersPerPix;
    ny1 = (pData->pExtents[1] - dy1) / pData->dMetersPerPix;
    nx2 = (dx2 - pData->pExtents[0]) / pData->dMetersPerPix;
    ny2 = (pData->pExtents[1] - dy2) / pData->dMetersPerPix;
    VectorWriter_bresenham(pData, nx1, ny1, nx2, ny2);
}

static const unsigned char* VectorWriter_processPoint(VectorWriterData *pData, const unsigned char *pWKB, int hasz)
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

static const unsigned char* VectorWriter_processLineString(VectorWriterData *pData, const unsigned char *pWKB, int hasz)
{
    GUInt32 nPoints, n;
    double dx1, dy1, dx2, dy2;

    READ_WKB_VAL(nPoints, pWKB)
    if( nPoints > 0 )
    {
        if( pData->nLineWidth > 0 )
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
        else
        {
            /* skip */
            pWKB += nPoints * (sizeof(double) * 2);
            if(hasz)
            {
                pWKB += nPoints * sizeof(double);
            }
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
static const unsigned char* VectorWriter_processLinearRing(VectorWriterData *pData, const unsigned char *pWKB, int hasz)
{
    GUInt32 nPoints, n;
    double dx1, dy1, dx2, dy2;
    double dFirstX, dFirstY;
    /* when pData->bFill */
    double *pPolyX, *pPolyY, *pConstant, *pMultiple;
    double dMinX, dMaxX, dMinY, dMaxY;
    int x, y;
    const unsigned char *pStartThisPoint = NULL;

    READ_WKB_VAL(nPoints, pWKB)
    if( nPoints > 0 )
    {
        /* Save this start so we can 'rewind' if we need to also do the outline */
        pStartThisPoint = pWKB;
        if( pData->bFill )
        {
            /* now do the fill */        
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
                    if( dx1 > dMaxX)
                        dMaxX = dx1;
                    if( dy1 < dMinY)
                        dMinY = dy1;
                    if( dy1 > dMaxY)
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
                
            /* Snap to the grid we are using */
            dMaxY = pData->pExtents[1] + (floor((pData->pExtents[1] - dMaxY) / pData->dMetersPerPix) * pData->dMetersPerPix);
            dMinX = pData->pExtents[0] + (floor((dMinX - pData->pExtents[0]) / pData->dMetersPerPix) * pData->dMetersPerPix);

            /* Use the centre of each pixel for the test */
            for( dy1 = (dMaxY -  pData->dMetersPerPix / 2); dy1 >= dMinY; dy1 -= pData->dMetersPerPix )
            {
                for( dx1 = (dMinX + pData->dMetersPerPix / 2); dx1 <= dMaxX; dx1 += pData->dMetersPerPix )
                {
                    if( pointInPolygon(nPoints, dx1, dy1, pPolyX, pPolyY,
                            pConstant, pMultiple) )
                    {
                        /* truncate ok for this as tl corner should relate to the centre of the pixel coord */
                        x = (dx1 - pData->pExtents[0]) / pData->dMetersPerPix;
                        y = (pData->pExtents[1] - dy1) / pData->dMetersPerPix;
                        /* Special function that ignores nLineWidth */
                        /* and only fills in where not set */
                        VectorWriter_plot_for_fill(pData, x, y);
                    }
                }
            }

            free(pPolyX);
            free(pPolyY);
            free(pConstant);
            free(pMultiple);

            
            /* now if the (old) nLineWidth is zero 'rub out' what we've done */
            /* Along the outline. Necessary since the centres of some pixels will be */
            /* within the poly but not completely. Rubbing out these partial pixels */
            /* along the outline should do the trick */
            if( pData->nLineWidth == 0 )
            {
                /* rewind to the start of the point (again) */
                pWKB = pStartThisPoint;

                /* set fill color to 0 */
                pData->nValueToBurn = 0;
                /* line width to 1 */
                pData->nLineWidth = 1;
                
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

                /* reset */
                pData->nValueToBurn = 1;
                pData->nLineWidth = 0;
            }
        }
        
        if( pData->nLineWidth > 0 )
        {
            /* rewind to the start of the point (in case we filled) */
            pWKB = pStartThisPoint;
                        
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
        
        if( pWKB == pStartThisPoint )
        {
            /* they must have passed fill=False and linewidth==0  */
            /* Must be just interested in points */
            /* read the data so pWKB valid for next feature */
            pWKB += nPoints * (sizeof(double) * 2);
            if(hasz)
            {
                pWKB += nPoints * sizeof(double);
            }
        }
    }
    return pWKB;
}

static const unsigned char* VectorWriter_processPolygon(VectorWriterData *pData, const unsigned char *pWKB, int hasz)
{
    GUInt32 nRings, n;

    READ_WKB_VAL(nRings, pWKB)
    for( n = 0; n < nRings; n++ )
    {
        pWKB = VectorWriter_processLinearRing(pData, pWKB, hasz);
    }
    return pWKB;
}

static const unsigned char* VectorWriter_processMultiPoint(VectorWriterData *pData, const unsigned char *pWKB, int hasz)
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

static const unsigned char* VectorWriter_processMultiLineString(VectorWriterData *pData, const unsigned char *pWKB, int hasz)
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

static const unsigned char* VectorWriter_processMultiPolygon(VectorWriterData *pData, const unsigned char *pWKB, int hasz)
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

static const unsigned char* VectorWriter_processWKB(VectorWriterData *pData, const unsigned char *pCurrWKB);

static const unsigned char* VectorWriter_processGeometryCollection(VectorWriterData *pData, const unsigned char *pWKB)
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

static const unsigned char* VectorWriter_processWKB(VectorWriterData *pData, const unsigned char *pCurrWKB)
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

#define GETSTATE(m) ((struct VectorRasterizerState*)PyModule_GetState(m))

/* Helper function */
int GetHalfCrossSize(PyObject *self)
{
    PyObject *pObj;
    int nHalfCrossSize = HALF_CROSS_SIZE, n;
    
    pObj = PyObject_GetAttrString(self, "HALF_CROSS_SIZE");
    if( pObj != NULL )
    {
        n = PyLong_AsLong(pObj);
        Py_DECREF(pObj);
        if( n != -1 )
            nHalfCrossSize = n;
    }
    
    return nHalfCrossSize;
}

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
    int n, bFill = 0, nHalfCrossSize;

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

    nHalfCrossSize = GetHalfCrossSize(self);

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
    pWriter = VectorWriter_create((PyArrayObject*)pOutArray, adExtents, nLineWidth, bFill, nHalfCrossSize);
    
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
    int n, bFill = 0, nHalfCrossSize;

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

    nHalfCrossSize = GetHalfCrossSize(self);

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
    pWriter = VectorWriter_create((PyArrayObject*)pOutArray, adExtents, nLineWidth, bFill, nHalfCrossSize);
    
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
    int n, bFill = 0, nHalfCrossSize;

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

    nHalfCrossSize = GetHalfCrossSize(self);

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
    pWriter = VectorWriter_create((PyArrayObject*)pOutArray, adExtents, nLineWidth, bFill, nHalfCrossSize);
    
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

static PyObject *vectorrasterizer_rasterizeWKB(PyObject *self, PyObject *args)
{
    const unsigned char *pszWKB = NULL;
    Py_ssize_t nWKBSize = 0;
    PyObject *pBBoxObject; /* must be a sequence*/
    int nXSize, nYSize, nLineWidth;
    double adExtents[4];
    PyObject *o;
    npy_intp dims[2];
    PyObject *pOutArray;
    VectorWriterData *pWriter;
    int n, bFill = 0, nHalfCrossSize;

    if( !PyArg_ParseTuple(args, "y#Oiii|i:rasterizeGeometry", &pszWKB, &nWKBSize,
            &pBBoxObject, &nXSize, &nYSize, &nLineWidth, &bFill))
        return NULL;

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
    
    nHalfCrossSize = GetHalfCrossSize(self);

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
    if( pszWKB != NULL )
    {
        pWriter = VectorWriter_create((PyArrayObject*)pOutArray, adExtents, nLineWidth, bFill, nHalfCrossSize);
    
        VectorWriter_processWKB(pWriter, pszWKB);

        VectorWriter_destroy(pWriter);
    }

    return pOutArray;
}

/* Our list of functions in this module*/
static PyMethodDef VectorRasterizerMethods[] = {
    {"rasterizeLayer", vectorrasterizer_rasterizeLayer, METH_VARARGS, 
"read an OGR dataset and vectorize outlines to numpy array:\n"
"call signature: arr = rasterizeLayer(ogrlayer, boundingbox, xsize, ysize, linewidth, sql, fill=False)\n"
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
"  boundingbox is a sequence that contains (tlx, tly, brx, bry)\n"
"  xsize,ysize size of output array\n"
"  linewidth is the width of the line\n"
"  fill is an optional argument that determines if polygons are filled in\n"},
    {"rasterizeGeometry", vectorrasterizer_rasterizeGeometry, METH_VARARGS,
"read an OGR Geometry and vectorize outlines to numpy array:\n"
"call signature: arr = rasterizeGeometry(ogrgeometry, boundingbox, xsize, ysize, fill=False)\n"
"where:\n"
"  ogrgeometry is an instance of ogr.Geometry\n"
"  boundingbox is a sequence that contains (tlx, tly, brx, bry)\n"
"  xsize,ysize size of output array\n"
"  linewidth is the width of the line\n"
"  fill is an optional argument that determines if polygons are filled in\n"},
    {"rasterizeWKB", vectorrasterizer_rasterizeWKB, METH_VARARGS,
"read an WKB from a bytes object and vectorize outlines to numpy array:\n"
"call signature: arr = rasterizeWKB(bytes, boundingbox, xsize, ysize, fill=False)\n"
"where:\n"
"  bytes is a bytes object (assumed to be correct endian).\n"
"  boundingbox is a sequence that contains (tlx, tly, brx, bry)\n"
"  xsize,ysize size of output array\n"
"  linewidth is the width of the line\n"
"  fill is an optional argument that determines if polygons are filled in\n"},
    {NULL}        /* Sentinel */
};

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

PyMODINIT_FUNC 
PyInit_vectorrasterizer(void)
{
    PyObject *pModule;
    struct VectorRasterizerState *state;

    /* initialize the numpy stuff */
    import_array();

    pModule = PyModule_Create(&moduledef);
    if( pModule == NULL )
        return NULL;

    state = GETSTATE(pModule);

    /* Create and add our exception type */
    state->error = PyErr_NewException("vectorrasterizer.error", NULL, NULL);
    if( state->error == NULL )
    {
        Py_DECREF(pModule);
        return NULL;
    }
    if( PyModule_AddObject(pModule, "error", state->error) != 0)
    {
        Py_DECREF(pModule);
        return NULL;
    }
    
    /* Constant for HALF_CROSS_SIZE */
    if( PyModule_AddIntMacro(pModule, HALF_CROSS_SIZE) != 0 )
    {
        Py_DECREF(pModule);
        return NULL;
    }

    return pModule;
}
