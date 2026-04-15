import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/auth/callback',
      name: 'AuthCallback',
      component: () => import('@/views/AuthCallback.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      component: () => import('@/layouts/DefaultLayout.vue'),
      children: [
        { path: '', name: 'Dashboard', component: () => import('@/views/DashboardView.vue') },
        { path: 'assets', name: 'Assets', component: () => import('@/views/AssetsView.vue') },
        { path: 'assets/:id', name: 'AssetDetail', component: () => import('@/views/AssetDetailView.vue') },
        { path: 'licenses', name: 'Licenses', component: () => import('@/views/LicensesView.vue') },
        { path: 'subscriptions', name: 'Subscriptions', component: () => import('@/views/SubscriptionsView.vue') },
        { path: 'ip-addresses', name: 'IPAddresses', component: () => import('@/views/IPAddressesView.vue') },
        { path: 'certificates', name: 'Certificates', component: () => import('@/views/CertificatesView.vue') },
        { path: 'consumables', name: 'Consumables', component: () => import('@/views/ConsumablesView.vue') },
        { path: 'maintenance', name: 'Maintenance', component: () => import('@/views/MaintenanceView.vue') },
        { path: 'racks', name: 'Racks', component: () => import('@/views/RacksView.vue') },
        { path: 'notifications', name: 'Notifications', component: () => import('@/views/NotificationsView.vue') },
        { path: 'audit-logs', name: 'AuditLogs', component: () => import('@/views/AuditLogsView.vue') },
        { path: 'categories', name: 'Categories', component: () => import('@/views/CategoriesView.vue') },
        { path: 'locations', name: 'Locations', component: () => import('@/views/LocationsView.vue') },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')
  if (!to.meta.public && !token) {
    return { name: 'Login' }
  }
})

export default router
