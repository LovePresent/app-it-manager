import 'axios'

declare module 'axios' {
  export interface AxiosRequestConfig<D = any> {
    skipGlobalLoading?: boolean
    loadingLabel?: string
  }

  export interface InternalAxiosRequestConfig<D = any> {
    skipGlobalLoading?: boolean
    loadingLabel?: string
    globalLoadingTaskId?: string
  }
}

export {}
